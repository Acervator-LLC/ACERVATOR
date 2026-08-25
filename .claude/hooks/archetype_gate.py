#!/usr/bin/env python3
"""Write|Edit archetype gate. One file, two modes.

MODES
=====
--pre   PreToolUse. Runs the archetype on the PENDING content and
        denies the write when that content introduces a high or
        critical finding the file does not have yet.
--post  PostToolUse (default). Runs the archetype on the file that was
        written and reports the verdict as additionalContext.

REGRESSION, NOT ABSOLUTE STATE
==============================
--pre blocks a rise, never a level. A file that already carries 90 high
findings stays editable; a write that adds the 91st does not land. The
comparison is a multiset of finding fingerprints, so swapping one high
for a different high is a rise even though the count is flat. A
fingerprint drops line numbers, so unrelated code movement is not a
rise.

Both sides of the comparison run the SAME archetype set. The set is the
union of the routing for the pending content and the routing for the
bytes on disk. Routing on the pending content is what makes a write that
ADDS a Qt widget or an indicator reach the GUI and TA archetypes.

PATH NORMALISATION
==================
The tool payload names the target. That name is attacker-controlled, so
the gate canonicalises it before it decides anything:

  - leading and trailing whitespace is stripped;
  - `~` is expanded;
  - on Windows a backslash is folded to a forward slash;
  - a trailing dot or space is stripped from every component, because
    Win32 drops those and `subject.py ` therefore names `subject.py`;
  - `..` is collapsed and the result is resolved;
  - a relative path is anchored at the repository root.

Without this, one trailing space gave a suffix that matched no
archetype, no archetype ran, and any content landed. That was a full
defeat of both modes.

NO VERDICT CACHE
================
An earlier build cached verdicts in `.archetype_baseline.json`, keyed by
content hash. The key pinned the bytes; nothing pinned the VERDICT to a
real measurement. The cache file was an ordinary file in the tree, so
two writes forged an entry that said "passed, no findings" for content
that carried seven high findings, and the gate believed it.

The cache is gone. Both sides of every comparison are measured on
demand.

Trade-off, stated plainly. Cost: --post can no longer reuse the
measurement --pre already made, so a write costs one extra archetype
fan-out. Measured 2026-08-10 on a seven-line file: --post 6.2 seconds,
--pre 7.1 seconds. Almost all of that is tool start-up, not file size.
On the largest trade file coding_archetype takes 47-49 seconds, so the
worst case is roughly 50 seconds of extra wall time on a write to that
file, inside the 240 second PostToolUse timeout. Benefit: there is no
longer any artefact on disk whose contents can make the gate skip a
measurement. An
optimisation that can be forged through the very tool the gate guards is
not an optimisation. Two alternatives were rejected: signing the cache
needs a key that lives in the same writable tree, and gating writes to
the cache path only closes the Write route while Bash stays open.

STAGING - MEASURING CONTENT THAT IS NOT ON DISK YET
===================================================
The pending content is staged at a sibling path and the archetype runs
there. A sibling keeps the directory, so every directory-sensitive rule
(the tests/ predicate, per-file ignores) grades the candidate the way it
would grade the original. The sibling name keeps the `test_` prefix and
the `_test.py` tail for the same reason.

Two failure modes are handled:

  - The staged name carries a random nonce and is recorded in a staging
    ledger under _logs. A run that Claude Code kills at its own hook
    timeout cannot reach its own cleanup, so the NEXT invocation reaps
    any stale staged file and any directory the staging created. Reaping
    is limited to names that match the staged-name pattern, so a forged
    ledger cannot delete real work.
  - Staging no longer creates a missing parent directory and leaves it
    behind. It records the directories it had to create and removes
    them, deepest first, and only while they are still empty. A deny
    leaves the tree exactly as it found it.

TOOL MATRIX
===========
A Claude Code matcher is a regex against the TOOL NAME, so the wiring
`Write|Edit` also matches MultiEdit and NotebookEdit. Both used to reach
a gate that did not understand their payload and returned "allow".

  Write        graded. tool_input.content is the pending content.
  Edit         graded. one old_string/new_string pair, applied to disk.
  MultiEdit    graded. tool_input.edits applied in order.
  NotebookEdit REFUSED. The archetypes grade files, not notebook cells,
               and a cell payload is not a file. --pre denies and says
               so. Silence would be a bypass.
  anything else whose name matches the wiring regex: REFUSED. An
               unknown editing tool is an ungradeable payload shape.
  anything else: allowed with a log line. A tool whose name holds
               neither "Write" nor "Edit" cannot write a file through
               this wiring.

WHAT PASSES THROUGH UNGRADED, AND WHY THAT IS NOT AN EVASION ROUTE
=================================================================
The gate fails CLOSED on every shape a real Write could present.

  DENIED  stdin unreadable, stdin that is not JSON, JSON that is not an
          object, a record with no tool_name. Claude Code always sends a
          JSON object carrying tool_name, so none of these shapes can
          come from a real tool call. Denying them costs nothing and
          removes the whole family of "send garbage, get an allow".
  DENIED  a graded tool whose payload carries no usable file_path, or a
          file_path that is not a string.
  DENIED  a graded tool whose pending content cannot be reconstructed,
          for example an Edit whose old_string is absent from the file.
          That Edit would fail anyway, so the deny costs no real work.
  DENIED  a graded write to the runtime directory or to a file whose
          name contains "credential". The gate must never read the
          credential store, so it cannot grade a write there. No product
          source lives under the runtime directory.
  ALLOWED a tool name that matches neither "Write" nor "Edit". Such a
          tool is not wired here and cannot write through this hook.
  ALLOWED a suffix no archetype grades, for example .json or .txt. No
          archetype can measure it, so there is no verdict to give. This
          is not an evasion route into Python: renaming the file
          afterwards needs Bash, and Bash is not wired to this hook at
          all. That is a gap in the WIRING, not in this gate.

--post never denies. It reports. On every shape above it stays silent
and writes a log line, because the write has already landed and a deny
would be theatre.

If stdin breaks for every call, every Write and Edit is denied. Bash is
not wired to this hook, so the operator can still repair
.claude/settings.json from Bash. That is the escape hatch.

THE SKIP LIST IS EMPTY
======================
Running an archetype makes no tool call, so the gate cannot recurse into
itself. Recursion therefore requires no exemption at all, and the list is
empty.

Every previous entry was removed, and each removal closed a route:

  - This file used to exempt itself. It now grades itself. A hook that
    cannot be measured is a hook nobody checks.
  - /docs/audits/ and "/Scaffolds and Hallucinations/" exempted whole
    directories by NAME. A real source file placed under either name was
    never graded. That is the evasion route.
  - .pytest_cache, .hypothesis, .mypy_cache and .ruff_cache hold no .py
    and no .md, so the entries never suppressed a real measurement and
    only offered four more directory names to hide under.
  - __pycache__ holds .pyc, not .py, and had the same shape.
  - The staged-sibling marker was a skip fragment, so any file a human
    named with that fragment was exempt for free. A staged sibling never
    reaches the skip test, so the fragment bought nothing.

CONTRACT
========
- stdin: the Claude Code tool record. Reads tool_name and tool_input.
- exit code: 0 on every path, in both modes. A deny rides in the stdout
  payload, never in the exit status. This is the mechanism
  verify_release_gate uses and it is measured to work here.
- --pre stdout on deny: {"decision": "deny", "reason": ...} plus the
  hookSpecificOutput form, so either Claude Code contract denies.
- --post stdout: hookSpecificOutput.additionalContext with the summary.
- Never crashes Claude Code. A crashed hook fails open and is worse
  than no hook.

DELIBERATE LIMITS
=================
- A tool the archetype marks `missing` is reported, not denied. Denying
  on a missing tool would brick a machine that lacks one linter. Both
  sides of the comparison run the same tool set, so the diff holds.
- If the archetype cannot run at all, the gate denies and names the
  recovery command. The operator escape is .claude/settings.json, which
  no archetype grades.

FALSIFICATION
=============
This gate is wrong if:
  (a) A .py file with a Qt widget base skips the GUI archetype.
  (b) A write that adds no high finding is denied.
  (c) A write that adds a high finding is allowed.
  (d) Any path returns a non-zero exit code.
  (e) A staged sibling, or a directory staging created, survives a run
      or survives the next invocation after a kill.
  (f) A trailing space, a MultiEdit, or a directory name makes a write
      skip measurement.
"""

from __future__ import annotations

import ast
import contextlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

with contextlib.suppress(AttributeError, ValueError):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parent.parent.parent

# Measured 2026-08-10: coding_archetype on the largest trade file took
# 47.0s, 46.7s and 49.1s over three samples. The old 30s limit meant the
# gate never ran on that file and still printed a green line from a
# second archetype. 180s is over 3x the slowest sample. The matching
# `timeout` on the hook entries in .claude/settings.json must stay above
# the budgets below, or Claude Code kills the hook first and the gate
# fails open.
TIMEOUT_S = 180

# Wall budget per hook invocation. The gate returns a verdict before
# Claude Code's own timeout can kill it.
PRE_BUDGET_S = 240
POST_BUDGET_S = 200

_SEVERE = ("critical", "high")


# ---------------------------------------------------------------------------
# Path normalisation
# ---------------------------------------------------------------------------


def _fold_component(part: str) -> str:
    """Drop the trailing dots and spaces Win32 drops from a component.

    `subject.py ` and `subject.py.` both open `subject.py` on Windows, so
    both must read as `subject.py` here. A component that is nothing but
    dots, such as `..`, is returned unchanged.
    """
    folded = part.rstrip(" .")
    return folded or part


def _normalise_raw_path(raw: object) -> str | None:
    """Canonical text form of the target a tool payload names.

    Returns None when the payload carries nothing usable as a path.
    """
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    text = os.path.expanduser(text)
    if os.name == "nt":
        text = text.replace("\\", "/")
    text = "/".join(_fold_component(p) for p in text.split("/"))
    return text or None


def _payload_path(data: dict) -> Path | None:
    """Absolute, canonical path of the file the tool call targets."""
    ti = data.get("tool_input")
    if not isinstance(ti, dict):
        return None
    raw = ti.get("file_path")
    if raw is None:
        raw = ti.get("path")
    if raw is None:
        raw = ti.get("notebook_path")
    text = _normalise_raw_path(raw)
    if text is None:
        return None
    p = Path(text)
    if not p.is_absolute():
        p = REPO / p
    p = Path(os.path.normpath(str(p)))
    with contextlib.suppress(OSError, RuntimeError, ValueError):
        p = p.resolve()
    return p


# ---------------------------------------------------------------------------
# Paths the gate must never read
# ---------------------------------------------------------------------------

# The runtime directory holds bot state and the credential store. The
# gate never opens anything there, so it cannot grade a write there, so
# it denies one instead. No product source lives under these names.
_FORBIDDEN_DIR_NAMES = (".acervator", ".acervator_logs")
_FORBIDDEN_NAME_FRAGMENT = "credential"


def _is_forbidden(path: Path) -> bool:
    """Report whether the gate must refuse to open this path."""
    if _FORBIDDEN_NAME_FRAGMENT in path.name.lower():
        return True
    lowered = {part.lower() for part in path.parts}
    return any(name in lowered for name in _FORBIDDEN_DIR_NAMES)


# ---------------------------------------------------------------------------
# Route by file type + content
# ---------------------------------------------------------------------------

_PY_SUFFIXES = (".py", ".pyw", ".pyi")
_MD_SUFFIXES = (".md", ".markdown")

_QT_BASES = frozenset(
    {
        "QWidget",
        "QDialog",
        "QMainWindow",
        "QFrame",
        "QPushButton",
        "QLineEdit",
        "QTextEdit",
        "QLabel",
        "QCheckBox",
        "QRadioButton",
        "QComboBox",
        "QGroupBox",
        "QScrollArea",
        "QDockWidget",
        "QTabWidget",
    }
)


def _read_text(path: Path) -> str:
    """File contents, or "" when the file cannot be read."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _src_has_qwidget_class(source: str, path: Path) -> bool:
    """Report whether source defines a class with a Qt widget base.

    Routes Python files to the GUI archetype as well as the coding one.
    """
    try:
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, ValueError):
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for b in node.bases:
            name = None
            if isinstance(b, ast.Name):
                name = b.id
            elif isinstance(b, ast.Attribute):
                name = b.attr
            if name in _QT_BASES:
                return True
    return False


# Names that mark a file as carrying technical-analysis maths or a
# chart. Used to add the TA archetype on top of the others.
_TA_MARKERS = (
    "indicator",
    "rsi",
    "macd",
    "bollinger",
    "adx",
    "vwap",
    "candle",
    "ohlc",
    "vortex",
    "ichimoku",
    "stochastic",
    "supertrend",
    "zscore",
    "atr",
    "ema",
    "sma",
    "wilder",
    "slingshot",
    "voting",
    "chart",
)


# How many TA markers must appear in a file body before the TA
# archetype is added on top of the others.
_TA_MARKER_QUORUM = 3

# How much of a file body the TA marker scan reads.
_TA_SCAN_CHARS = 20000


def _looks_like_ta(path: Path, source: str) -> bool:
    """Report whether the file computes indicators or draws a chart."""
    name = path.name.lower()
    if any(m in name for m in _TA_MARKERS):
        return True
    head = source[:_TA_SCAN_CHARS].lower()
    return sum(1 for m in _TA_MARKERS if m in head) >= _TA_MARKER_QUORUM


def _pick_archetypes(path: Path, source: str) -> list:
    """EVERY archetype that applies, not the first one that matches.

    v3.24.99 - this returned ONE module. A .py file with a Qt widget got
    `gui_archetype` and nothing else.

    MEASURED 2026-08-09: `gui_archetype` runs 3 tools (gui-static, ruff,
    bandit); `coding_archetype` runs 6 (ruff, mypy, pyright, bandit,
    vulture, semgrep). The GUI archetype omits mypy, pyright, vulture
    and semgrep, so NO file under src/gui/ was ever type-checked or
    dead-code-checked. On four of its files 10 high findings were
    invisible - 7 `reportOptionalCall` and 3 dead imports - and a clean
    "0 high" sweep across the whole tab meant nothing.

    Operator, 2026-08-09: "Should be all four...GUI, Coding, TA (Chart +
    Quant), Docs."

    `source` is the content to route on. --pre passes the PENDING
    content, so a write that ADDS a Qt widget or an indicator reaches
    the GUI and TA archetypes. Routing on the bytes already on disk let
    that write through with only the coding archetype.
    """
    suffix = path.suffix.lower()
    mods = []
    if suffix in _PY_SUFFIXES:
        # Coding ALWAYS. A GUI file is still Python.
        mods.append("tools.harness.coding_archetype")
        if _src_has_qwidget_class(source, path):
            mods.append("tools.harness.gui_archetype")
        if _looks_like_ta(path, source):
            mods.append("tools.harness.ta_archetype")
    elif suffix in _MD_SUFFIXES:
        mods.append("tools.harness.docs_archetype")
    return mods


def _module_union(path: Path, pending: str) -> list:
    """Archetypes that apply to the pending content or to the disk copy.

    Both sides of a regression comparison must run the same set, or a
    module that only one side ran turns every one of its findings into a
    false rise or a false pass.
    """
    both = set(_pick_archetypes(path, pending))
    if path.exists():
        both |= set(_pick_archetypes(path, _read_text(path)))
    return sorted(both)


# ---------------------------------------------------------------------------
# Staging ledger - survive a kill
# ---------------------------------------------------------------------------

# Marks a staged sibling. The nonce makes the name unguessable, so the
# reaper can delete a leftover without ever touching real work.
_SHADOW_MARKER = "_acv_shadow"
_SHADOW_NONCE_CHARS = 12
_SHADOW_RE = re.compile(
    re.escape(_SHADOW_MARKER) + r"_[0-9a-f]{" + str(_SHADOW_NONCE_CHARS) + r"}"
)

LEDGER_PATH = REPO / "_logs" / "archetype_gate_staging.json"

# A leftover younger than this may belong to a run that is still going,
# so the reaper leaves it alone.
STAGING_GRACE_S = 90

# Ledger records older than this are dropped even when their files are
# already gone, so the file cannot grow without bound.
LEDGER_MAX_AGE_S = 24 * 60 * 60


def _now_iso() -> str:
    """Return UTC now in the log and ledger timestamp format."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _debug_log(line: str) -> None:
    """Filesystem receipt so the operator can verify the hook fires.

    Log path is stable so the operator can `tail -f` it during a session.
    """
    try:
        log_dir = REPO / "_logs"
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "archetype_gate.log"
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{_now_iso()}] {line}\n")
    except OSError:
        pass


def _ledger_load() -> list:
    """Every staging record on disk. A damaged ledger reads as empty."""
    try:
        data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return []
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def _ledger_write(records: list) -> None:
    """Replace the ledger. A write failure is logged, never raised."""
    try:
        LEDGER_PATH.parent.mkdir(exist_ok=True)
        LEDGER_PATH.write_text(json.dumps(records, indent=1), encoding="utf-8")
    except OSError as exc:
        _debug_log(f"staging ledger write failed: {exc}")


def _ledger_add(record: dict) -> None:
    """Record a staging attempt BEFORE the files are created."""
    records = _ledger_load()
    records.append(record)
    _ledger_write(records)


def _ledger_drop(record_id: str) -> None:
    """Forget a staging record whose cleanup already succeeded."""
    _ledger_write([r for r in _ledger_load() if r.get("id") != record_id])


def _age_seconds(stamp: object) -> float:
    """Age of a ledger timestamp. Unparseable reads as infinitely old."""
    if not isinstance(stamp, str):
        return float("inf")
    try:
        when = datetime.fromisoformat(stamp)
    except ValueError:
        return float("inf")
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return (datetime.now(UTC) - when).total_seconds()


def _reap_file(raw: object) -> bool:
    """Delete one staged sibling. Refuses any name that is not staged."""
    if not isinstance(raw, str):
        return False
    p = Path(raw)
    if not _SHADOW_RE.search(p.name):
        return False
    try:
        if p.is_file():
            p.unlink()
            return True
    except OSError:
        return False
    return False


def _reap_dirs(raws: object) -> None:
    """Remove directories staging created, deepest first, while empty."""
    if not isinstance(raws, list):
        return
    for raw in sorted((r for r in raws if isinstance(r, str)), reverse=True):
        with contextlib.suppress(OSError):
            Path(raw).rmdir()


def _reap_stale_staging() -> None:
    """Undo what a killed run left behind.

    Claude Code kills a hook at its own timeout, and a killed process
    never reaches its cleanup. That is exactly the case staging has to
    survive, so cleanup cannot live only in a finally block. Every
    invocation reaps first.

    Deletion is limited to names that match the staged-name pattern and
    to directories that are already empty, so a forged ledger cannot
    destroy real work.
    """
    records = _ledger_load()
    if not records:
        return
    kept = []
    for rec in records:
        age = _age_seconds(rec.get("created"))
        if age < STAGING_GRACE_S:
            kept.append(rec)
            continue
        reaped = [f for f in rec.get("files", []) if _reap_file(f)]
        _reap_dirs(rec.get("dirs"))
        if reaped:
            _debug_log(f"reaped stale staging: {', '.join(reaped)}")
        if age < LEDGER_MAX_AGE_S and not reaped:
            kept.append(rec)
    if len(kept) != len(records):
        _ledger_write(kept)


def _sweep_directory(directory: Path, keep: Path) -> None:
    """Reap a stale staged sibling sitting in the directory in use.

    The ledger is the primary mechanism. This is the cheap second one: a
    leftover in the very directory being staged into is found on the
    next write to that directory, without a tree walk.
    """
    with contextlib.suppress(OSError):
        for entry in directory.iterdir():
            if entry == keep or not _SHADOW_RE.search(entry.name):
                continue
            try:
                stale = (time.time() - entry.stat().st_mtime) > STAGING_GRACE_S
            except OSError:
                continue
            if stale and _reap_file(str(entry)):
                _debug_log(f"swept stale staged sibling: {entry.name}")


# ---------------------------------------------------------------------------
# Run an archetype subprocess
# ---------------------------------------------------------------------------


def _remaining(deadline: float | None) -> float:
    """Seconds left before the hook must return. None means unbounded."""
    if deadline is None:
        return float(TIMEOUT_S)
    return deadline - time.monotonic()


def _swap_paths(text: str, staged: Path, real: Path) -> str:
    """Rewrite a staged sibling's name back to the real name.

    Applied to raw archetype stdout, so JSON escaping is handled by
    comparing the escaped forms. Keeps a reported path readable and keeps
    fingerprints stable across the two sides of a comparison.
    """
    pairs = (
        (json.dumps(str(staged))[1:-1], json.dumps(str(real))[1:-1]),
        (staged.name, real.name),
        (staged.stem, real.stem),
    )
    for old, new in pairs:
        text = text.replace(old, new)
    return text


def _run_archetype(
    module: str,
    target: Path,
    rewrite_to: Path | None = None,
    deadline: float | None = None,
) -> dict:
    """Return the archetype's JSON report, or a dict carrying `_error`."""
    budget = _remaining(deadline)
    if budget <= 1.0:
        return {"_error": f"archetype {module} skipped: hook wall budget spent"}
    try:
        # v3.23.94 justification: module is one of a hardcoded set
        # chosen by _pick_archetypes from the file's suffix + content.
        # target is a Path built by _payload_path from Claude Code's
        # stdin contract, or a sibling this module staged.
        # sys.executable is the running interpreter, an absolute path.
        # No shell=True. S603 is a false positive here.
        proc = subprocess.run(  # noqa: S603
            [sys.executable, "-m", module, str(target)],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            timeout=min(float(TIMEOUT_S), budget),
        )
    except subprocess.TimeoutExpired:
        return {"_error": f"archetype {module} timed out after {TIMEOUT_S}s"}
    except (OSError, ValueError) as e:
        return {
            "_error": (f"archetype {module} failed to start: {type(e).__name__}: {e}")
        }
    text = proc.stdout
    if not text.strip():
        return {
            "_error": (
                f"archetype {module} produced no output; "
                f"stderr: {proc.stderr[:200]}"
            )
        }
    if rewrite_to is not None:
        text = _swap_paths(text, target, rewrite_to)
    try:
        report = json.loads(text)
    except json.JSONDecodeError:
        return {"_error": f"archetype {module} produced non-JSON output"}
    if not isinstance(report, dict):
        return {"_error": f"archetype {module} produced a non-object report"}
    return report


# ---------------------------------------------------------------------------
# Staging - measure content that is not on disk yet
# ---------------------------------------------------------------------------


def _staged_path(real: Path) -> Path:
    """Sibling path used to grade pending content.

    The name keeps the `test_` prefix and the `_test.py` tail, because
    the archetype changes which tools it runs for a test file. The
    directory is unchanged, so every directory-based rule exemption
    still applies. The nonce makes the name unguessable, which is what
    lets the reaper delete a leftover safely.
    """
    nonce = secrets.token_hex(_SHADOW_NONCE_CHARS // 2)
    mark = f"{_SHADOW_MARKER}_{nonce}"
    stem, suffix = real.stem, real.suffix
    if stem.endswith("_test"):
        head = stem[: -len("_test")]
        return real.with_name(f"{head}{mark}_test{suffix}")
    return real.with_name(f"{stem}{mark}{suffix}")


def _missing_ancestors(directory: Path) -> list:
    """Directories that do not exist yet, outermost first.

    Staging must not leave a directory behind when the gate then denies,
    so it has to know exactly which ones it created.
    """
    missing = []
    node = directory
    while not node.exists():
        missing.append(node)
        parent = node.parent
        if parent == node:
            break
        node = parent
    missing.reverse()
    return missing


def _evaluate_content(
    real: Path,
    content: str,
    modules: list,
    deadline: float | None = None,
) -> dict:
    """Grade `content` as if it were the file at `real`.

    Returns {module: report}. The staged sibling and every directory
    staging had to create are removed before this returns, and are
    recorded in the ledger so a killed run is cleaned up on the next
    invocation.
    """
    staged = _staged_path(real)
    created = _missing_ancestors(staged.parent)
    record = {
        "id": staged.name,
        "created": _now_iso(),
        "files": [str(staged)],
        "dirs": [str(d) for d in created],
    }
    _ledger_add(record)
    reports: dict = {}
    try:
        for node in created:
            node.mkdir()
        _sweep_directory(staged.parent, staged)
        staged.write_text(content, encoding="utf-8", errors="replace")
    except OSError as exc:
        _cleanup_staging(staged, created, record)
        return {"_staging": {"_error": f"cannot stage pending content: {exc}"}}
    try:
        for module in modules:
            reports[module] = _run_archetype(
                module, staged, rewrite_to=real, deadline=deadline
            )
    finally:
        _cleanup_staging(staged, created, record)
    return reports


def _cleanup_staging(staged: Path, created: list, record: dict) -> None:
    """Remove the staged sibling and any directory staging created."""
    with contextlib.suppress(OSError):
        staged.unlink()
    for node in reversed(created):
        with contextlib.suppress(OSError):
            node.rmdir()
    _ledger_drop(str(record.get("id")))


# ---------------------------------------------------------------------------
# Finding identity + regression arithmetic
# ---------------------------------------------------------------------------

_DIGITS = re.compile(r"\d+")


def _fingerprint(finding: dict) -> str:
    """Identity that survives an unrelated line shift.

    Line numbers are excluded, so moving code does not read as a new
    finding. Digits inside the message are folded for the same reason.
    """
    msg = _DIGITS.sub("#", str(finding.get("message") or ""))[:160]
    return f"{finding.get('tool')}|{finding.get('rule_id')}|{msg}"


def _first_error(reports: dict) -> str:
    """First evaluation failure across a {module: report} map, or ""."""
    for report in reports.values():
        if isinstance(report, dict) and "_error" in report:
            return str(report["_error"])
    return ""


def _high_fingerprints(reports: dict) -> list:
    """Sorted fingerprints of every high or critical finding."""
    out: list = []
    for report in reports.values():
        out.extend(
            _fingerprint(f)
            for f in report.get("findings", [])
            if isinstance(f, dict) and f.get("severity") in _SEVERE
        )
    return sorted(out)


def _introduced(after: list, before: list) -> list:
    """Multiset difference. Duplicating an existing high counts as new."""
    pool = Counter(before)
    new: list = []
    for fp in after:
        if pool[fp] > 0:
            pool[fp] -= 1
        else:
            new.append(fp)
    return new


def _missing_tools(reports: dict) -> list:
    """Tools the archetype could not run. Reported, never denied on."""
    out: set = set()
    for report in reports.values():
        avail = report.get("tool_availability", {})
        if isinstance(avail, dict):
            out.update(t for t, s in avail.items() if s in ("missing", "error"))
    return sorted(out)


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------

# How many findings the deny text and the report text name before they
# truncate.
_DENY_LIST_CAP = 5


def _summarize(report: dict, module: str, target: Path) -> str:
    """Render one archetype report as the text --post injects."""
    if "_error" in report:
        return (
            f"[archetype-gate] {module} on {target.name}: {report['_error']}\n"
            "  (this is a hook-side issue; the write itself succeeded.)"
        )
    passed = report.get("passed", False)
    by_sev = report.get("by_severity", {})
    total = sum(by_sev.values())
    by_tool = report.get("by_tool", {})
    tool_avail = report.get("tool_availability", {})
    missing = [t for t, s in tool_avail.items() if s == "missing"]
    errored = [t for t, s in tool_avail.items() if s == "error"]

    verdict_line = "[archetype-gate] " + (
        f"OK - {module} on {target.name}: passed=True "
        f"({total} findings, no high/critical)"
        if passed
        else f"FAIL - {module} on {target.name}: passed=False ({total} findings)"
    )
    lines = [verdict_line]
    if by_sev:
        parts = [f"{sev}={n}" for sev, n in sorted(by_sev.items())]
        lines.append(f"  severity: {', '.join(parts)}")
    if by_tool:
        parts = [f"{t}={n}" for t, n in sorted(by_tool.items())]
        lines.append(f"  by tool: {', '.join(parts)}")
    if missing:
        lines.append(f"  tools missing: {', '.join(missing)}")
    if errored:
        lines.append(f"  tools errored: {', '.join(errored)}")
    if not passed:
        lines.append(
            "  fix or explicitly acknowledge before self-reporting the task done."
        )
        findings = report.get("findings", [])
        highs = [f for f in findings if f.get("severity") in _SEVERE][:_DENY_LIST_CAP]
        if highs:
            lines.append("  top findings:")
            lines.extend(
                f"    - {f.get('tool')}:{f.get('rule_id')} "
                f"line {f.get('line')} [{f.get('severity')}]: "
                f"{(f.get('message') or '')[:100]}"
                for f in highs
            )
    return "\n".join(lines)


def _rel(path: Path) -> str:
    """Repo-relative posix path, for text a human has to retype."""
    try:
        return path.resolve().relative_to(REPO).as_posix()
    except (ValueError, OSError):
        return path.name


def _deny_reason(
    path: Path,
    new: list,
    counts: tuple,
    module: str,
    missing: list,
) -> str:
    """Build the deny text. `counts` is (before_high, after_high)."""
    rel = _rel(path)
    before_n, after_n = counts
    lines = [
        (
            f"Archetype-gate DENY: this write introduces {len(new)} "
            f"high/critical finding(s) that {rel} does not carry now."
        )
    ]
    for fp in new[:_DENY_LIST_CAP]:
        tool, _, rest = fp.partition("|")
        rule, _, msg = rest.partition("|")
        lines.append(f"  + {tool}:{rule} - {msg[:110]}")
    if len(new) > _DENY_LIST_CAP:
        lines.append(f"  + ... and {len(new) - _DENY_LIST_CAP} more")
    lines.append(f"on disk: {before_n} high/critical. pending: {after_n}.")
    lines.append(
        "The gate blocks a RISE, not a level. Pre-existing findings do not "
        "block; fix only what this write adds, then write again."
    )
    lines.append(f"Full report: python -m {module} {rel}")
    if missing:
        lines.append(f"Reduced coverage this run: {', '.join(missing)}.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# stdin helpers
# ---------------------------------------------------------------------------


def _payload(stdin_text: str) -> dict | None:
    """Parse the hook record. None means the record is not an object."""
    try:
        data = json.loads(stdin_text)
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _pending_content(data: dict, path: Path) -> str | None:
    """Reconstruct what the file will hold if this tool call lands.

    Returns None when the call cannot be simulated. The caller denies on
    None, because content the gate cannot reconstruct is content it
    cannot grade.
    """
    ti = data.get("tool_input")
    if not isinstance(ti, dict):
        return None
    if data.get("tool_name") == "Write":
        content = ti.get("content")
        return content if isinstance(content, str) else None
    current = ""
    if path.exists():
        try:
            current = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
    edits = ti.get("edits")
    if not isinstance(edits, list):
        edits = [ti]
    if not edits:
        return None
    for edit in edits:
        if not isinstance(edit, dict):
            return None
        old = edit.get("old_string")
        new = edit.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str) or not old:
            return None
        if old not in current:
            return None
        current = current.replace(old, new, -1 if edit.get("replace_all") else 1)
    return current


# ---------------------------------------------------------------------------
# Tool classification
# ---------------------------------------------------------------------------

# Payload shapes this gate understands.
_GRADED_TOOLS = ("Write", "Edit", "MultiEdit")

# The archetypes grade files. A notebook cell payload is not a file, so
# the gate refuses it out loud instead of waving it through.
_REFUSED_TOOLS = ("NotebookEdit",)

# The matcher in .claude/settings.json. Any tool name this matches
# reaches the gate, so any name it matches must be handled or refused.
_WIRING_RE = re.compile(r"Write|Edit")


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


def _emit_deny(reason: str) -> int:
    """Deny in both Claude Code contracts. Exit code stays 0."""
    payload = {
        "decision": "deny",
        "reason": reason,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
    }
    print(json.dumps(payload))
    _debug_log("pre: DENY " + reason.splitlines()[0])
    return 0


def _emit_note(text: str) -> int:
    """Report something --post noticed. --post never denies."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": text,
        },
    }
    print(json.dumps(payload))
    return 0


def _reject(mode: str, reason: str) -> int:
    """Deny in --pre, log in --post. The one place that choice is made."""
    if mode == "pre":
        return _emit_deny(reason)
    _debug_log("post: " + reason.splitlines()[0])
    return 0


def _baseline_reports(
    path: Path,
    modules: list,
    deadline: float | None,
) -> dict | None:
    """Verdict for the bytes currently on disk. None when unreadable."""
    if not path.exists():
        return {}
    try:
        current = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return _evaluate_content(path, current, modules, deadline=deadline)


def _run_pre(data: dict) -> int:
    """Deny the pending write when it introduces a high or critical."""
    path = _payload_path(data)
    if path is None:
        return _emit_deny(
            "Archetype-gate DENY: this tool call names no usable file_path, "
            "so the gate cannot tell which file it would change and cannot "
            "grade it. Reissue the write with an explicit file path."
        )
    if _is_forbidden(path):
        return _emit_deny(
            f"Archetype-gate DENY: {path.name} sits in the runtime or "
            "credential area. The gate never opens those paths, so it cannot "
            "grade this write. Write into the repository instead."
        )
    content = _pending_content(data, path)
    if content is None:
        return _emit_deny(
            f"Archetype-gate DENY: the gate cannot reconstruct what "
            f"{_rel(path)} would hold after this call, so it cannot grade it. "
            "For an Edit this usually means old_string is not in the file, "
            "which would fail the edit anyway. Re-read the file and retry."
        )
    modules = _module_union(path, content)
    if not modules:
        _debug_log(f"pre: allow {path.name} - no archetype for this suffix")
        return 0

    deadline = time.monotonic() + PRE_BUDGET_S
    after = _evaluate_content(path, content, modules, deadline=deadline)
    err = _first_error(after)
    if err:
        return _emit_deny(
            f"Archetype-gate DENY: cannot grade the pending write to "
            f"{_rel(path)}. {err}\n"
            "Work the harness did not evaluate is INVALID, so the write is "
            "held. Fix the harness, then write again:\n"
            f"  python -m {modules[0]} {_rel(path)}"
        )

    after_fps = _high_fingerprints(after)
    if not after_fps:
        _debug_log(f"pre: allow {path.name} (0 high in pending content)")
        return 0

    before = _baseline_reports(path, modules, deadline)
    if before is None or _first_error(before):
        return _emit_deny(
            f"Archetype-gate DENY: the pending write to {_rel(path)} carries "
            f"{len(after_fps)} high/critical finding(s) and the on-disk "
            "baseline could not be measured, so a rise cannot be ruled out.\n"
            f"  {_first_error(before or {}) or 'baseline unreadable'}\n"
            f"Run: python -m {modules[0]} {_rel(path)}"
        )

    before_fps = _high_fingerprints(before)
    new = _introduced(after_fps, before_fps)
    if not new:
        _debug_log(
            f"pre: allow {path.name} "
            f"(high {len(before_fps)} -> {len(after_fps)}, none new)"
        )
        return 0
    return _emit_deny(
        _deny_reason(
            path,
            new,
            (len(before_fps), len(after_fps)),
            modules[0],
            _missing_tools(after),
        )
    )


def _run_post(data: dict) -> int:
    """Report the archetype verdict for the file that was written."""
    path = _payload_path(data)
    if path is None or not path.exists():
        _debug_log(f"post: skipped, path missing (resolved to {path})")
        return 0
    if _is_forbidden(path):
        _debug_log(f"post: skipped {path.name} (runtime or credential area)")
        return 0
    modules = _pick_archetypes(path, _read_text(path))
    if not modules:
        _debug_log(f"post: skipped {path.name} - no archetype for this suffix")
        return 0

    deadline = time.monotonic() + POST_BUDGET_S
    parts = []
    for module in modules:
        _debug_log(f"post: running {module} on {path.name}")
        parts.append(
            _summarize(_run_archetype(module, path, deadline=deadline), module, path)
        )
    if not parts:
        return 0
    summary = "\n".join(parts)
    _debug_log(f"post: emitted JSON summary ({len(summary)} chars)")
    return _emit_note(summary)


def _classify(mode: str, name: object) -> int | None:
    """Handle a tool this gate does not grade. None means carry on."""
    if not isinstance(name, str) or not name:
        return _reject(
            mode,
            (
                "Archetype-gate DENY: this hook record carries no tool_name, so "
                "the gate cannot tell what the call would do. Claude Code always "
                "sends one, so this record did not come from a real tool call."
            ),
        )
    if name in _GRADED_TOOLS:
        return None
    if name in _REFUSED_TOOLS or _WIRING_RE.search(name):
        return _reject(
            mode,
            (
                f"Archetype-gate DENY: {name} reaches this gate through the "
                "Write|Edit matcher, and the gate does not understand its payload "
                "shape, so it cannot grade the result. Use Write, Edit or "
                "MultiEdit, which the gate grades."
            ),
        )
    _debug_log(f"skipped: tool={name!r} (not an editing tool)")
    return 0


def main(argv: list | None = None) -> int:
    """Entry point. `--pre` selects the deny gate, otherwise report."""
    args = list(sys.argv[1:] if argv is None else argv)
    mode = "pre" if "--pre" in args else "post"
    _debug_log(f"--- hook invoked ({mode}) ---")
    with contextlib.suppress(OSError, ValueError):
        _reap_stale_staging()
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return _reject(
            mode,
            (
                "Archetype-gate DENY: the gate could not read the hook record on "
                "stdin, so it graded nothing. Work the harness did not evaluate "
                "is INVALID. Bash is not wired to this hook, so repair "
                ".claude/settings.json from Bash if this persists."
            ),
        )
    data = _payload(raw)
    if data is None:
        return _reject(
            mode,
            (
                "Archetype-gate DENY: the hook record on stdin is not a JSON "
                "object, so the gate cannot tell which file this call would "
                "change. Claude Code always sends a JSON object, so this record "
                "did not come from a real tool call."
            ),
        )
    handled = _classify(mode, data.get("tool_name"))
    if handled is not None:
        return handled
    if mode == "pre":
        return _run_pre(data)
    return _run_post(data)


if __name__ == "__main__":
    sys.exit(main())

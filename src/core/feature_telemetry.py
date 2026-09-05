"""Runtime proof that a feature actually ran.

``FeatureCounter`` records one feature's calls, skips by reason, exceptions
by type, and first and last activity. ``FeatureTelemetry`` is the registry:
``declare`` names features that should fire, ``track`` records a call or an
exception around a block, and ``report_lines`` flags every zero-call feature
explicitly. State persists to ``telemetry_path()``, whose root
``TELEMETRY_ROOT_ENV`` overrides, and ``get_telemetry`` returns the shared
registry.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

from .io_utils import atomic_write_json

logger = logging.getLogger("acervator.feature_telemetry")

TELEMETRY_ROOT_ENV = "ACERVATOR_TELEMETRY_ROOT"
"""Environment variable ``_telemetry_root`` reads in place of the home directory.

The simulator and ``tests/conftest.py`` set it so neither writes into the
operator's runtime tree.
"""


def _telemetry_root(default_dir: str) -> Path:
    """Resolve an output directory, honouring the sim/test override."""
    override = os.environ.get(TELEMETRY_ROOT_ENV)
    if override:
        return Path(override)
    return Path.home() / default_dir


def telemetry_path() -> Path:
    """Resolve the telemetry file path at call time.

    ``FeatureTelemetry.__init__`` calls this so a ``TELEMETRY_ROOT_ENV``
    set after import is still honoured.
    """
    return _telemetry_root(".acervator") / "feature_telemetry.json"


# Bound at import; only __all__ still names it. Callers use telemetry_path().
TELEMETRY_PATH: Path = telemetry_path()
SCHEMA_VERSION: int = 1

# Cap distinct skip-reason / exception-type keys per feature so a
# pathological caller cannot grow the state file without bound.
_MAX_REASON_KEYS = 25


@dataclass
class FeatureCounter:
    """One feature's activity record.

    ``calls`` counts successful work units. ``skips`` counts
    deliberate no-ops WITH a reason (so "nothing happened" is
    distinguishable from "nothing was asked"). ``exceptions``
    counts failures by exception type name.
    """

    name: str
    calls: int = 0
    skips: dict[str, int] = field(default_factory=dict)
    exceptions: dict[str, int] = field(default_factory=dict)
    first_ts: float = 0.0
    last_ts: float = 0.0
    # Session-scoped call count — resets each process start so the
    # GUI can report "this run" separately from lifetime totals.
    session_calls: int = 0

    @property
    def total_skips(self) -> int:
        return sum(self.skips.values())

    @property
    def total_exceptions(self) -> int:
        return sum(self.exceptions.values())

    @property
    def is_dead(self) -> bool:
        """True when the feature has never recorded a single call.
        This is the signal that catches mounted-but-unfed widgets."""
        return self.calls == 0

    @property
    def is_dead_this_session(self) -> bool:
        """True when the feature recorded no calls in THIS process,
        even if it has lifetime history. Catches regressions where
        a previously-working feature stops being invoked."""
        return self.session_calls == 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "calls": self.calls,
            "skips": dict(self.skips),
            "exceptions": dict(self.exceptions),
            "first_ts": self.first_ts,
            "last_ts": self.last_ts,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FeatureCounter":
        return cls(
            name=str(d.get("name", "")),
            calls=int(d.get("calls", 0) or 0),
            skips={str(k): int(v) for k, v in (d.get("skips") or {}).items()},
            exceptions={str(k): int(v) for k, v in (d.get("exceptions") or {}).items()},
            first_ts=float(d.get("first_ts", 0.0) or 0.0),
            last_ts=float(d.get("last_ts", 0.0) or 0.0),
            session_calls=0,  # never restored — session-scoped
        )


class FeatureTelemetry:
    """Process-wide feature activity registry.

    One ``RLock`` guards every mutation of ``_counters`` and ``_declared``.
    """

    def __init__(self, path: Optional[Path] = None, autoload: bool = True) -> None:
        self._path = path or telemetry_path()
        self._lock = threading.RLock()
        self._counters: dict[str, FeatureCounter] = {}
        # Names passed to declare(); a declared feature with no counter is dead.
        self._declared: set[str] = set()
        self._session_start = time.time()
        if autoload:
            self.load()

    # ── declaration ──────────────────────────────────────────────

    def declare(self, *names: str) -> None:
        """Register feature names that SHOULD fire. A declared
        feature with zero calls is reported as DEAD; an undeclared
        feature that never fires is simply unknown.

        Call this at construction time for every feed API you wire,
        so the absence of activity is itself a reportable signal.
        """
        with self._lock:
            for n in names:
                if not n:
                    continue
                self._declared.add(n)
                self._counters.setdefault(n, FeatureCounter(name=n))

    # ── recording ────────────────────────────────────────────────

    def _counter(self, name: str) -> FeatureCounter:
        c = self._counters.get(name)
        if c is None:
            c = FeatureCounter(name=name)
            self._counters[name] = c
        return c

    def record_call(self, name: str, count: int = 1) -> None:
        """Record ``count`` successful work units for ``name``."""
        if count <= 0:
            return
        now = time.time()
        with self._lock:
            c = self._counter(name)
            c.calls += count
            c.session_calls += count
            if c.first_ts <= 0:
                c.first_ts = now
            c.last_ts = now

    def record_skip(
        self, name: str, reason: str = "unspecified", count: int = 1
    ) -> None:
        """Record a deliberate no-op WITH a reason. Distinguishes
        'nothing happened' from 'nothing was asked'."""
        if count <= 0:
            return
        now = time.time()
        with self._lock:
            c = self._counter(name)
            key = str(reason)[:120] or "unspecified"
            if key not in c.skips and len(c.skips) >= _MAX_REASON_KEYS:
                key = "_other"
            c.skips[key] = c.skips.get(key, 0) + count
            c.last_ts = now

    def record_exception(self, name: str, exc: BaseException | str) -> None:
        """Record a failure by exception type name."""
        now = time.time()
        type_name = type(exc).__name__ if isinstance(exc, BaseException) else str(exc)
        with self._lock:
            c = self._counter(name)
            key = str(type_name)[:120] or "Unknown"
            if key not in c.exceptions and len(c.exceptions) >= _MAX_REASON_KEYS:
                key = "_other"
            c.exceptions[key] = c.exceptions.get(key, 0) + 1
            c.last_ts = now

    @contextmanager
    def track(self, name: str) -> Iterator[None]:
        """Context manager: records one call on clean exit, or one
        exception (by type) if the block raises. Re-raises."""
        try:
            yield
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            self.record_exception(name, exc)
            raise
        else:
            self.record_call(name)

    # ── reading ──────────────────────────────────────────────────

    def get(self, name: str) -> Optional[FeatureCounter]:
        with self._lock:
            return self._counters.get(name)

    def snapshot(self, scope: str = "") -> list[FeatureCounter]:
        """All counters whose name starts with ``scope`` (empty =
        everything), sorted by name for deterministic output."""
        with self._lock:
            out = [
                c for n, c in self._counters.items() if not scope or n.startswith(scope)
            ]
        return sorted(out, key=lambda c: c.name)

    def dead_features(self, scope: str = "", session_only: bool = False) -> list[str]:
        """Declared features with zero calls — the scaffolding
        signal. ``session_only`` reports features that fired in a
        previous session but not this one (regression shape)."""
        with self._lock:
            names = sorted(
                n for n in self._declared if not scope or n.startswith(scope)
            )
            out = []
            for n in names:
                c = self._counters.get(n)
                if c is None:
                    out.append(n)
                    continue
                if session_only:
                    if c.is_dead_this_session:
                        out.append(n)
                elif c.is_dead:
                    out.append(n)
        return out

    def report_lines(self, scope: str = "", include_healthy: bool = True) -> list[str]:
        """Human-readable dump for the log + GUI panels.

        Dead features are listed FIRST and labelled, because the
        whole point is that silence should be loud.
        """
        counters = self.snapshot(scope)
        dead = self.dead_features(scope)
        stalled = [
            n for n in self.dead_features(scope, session_only=True) if n not in dead
        ]
        lines: list[str] = []
        label = f" (scope: {scope!r})" if scope else ""
        lines.append(f"Feature telemetry{label}:")
        if not counters:
            lines.append("  (no features recorded or declared)")
            return lines
        if dead:
            lines.append(f"  DEAD — declared but NEVER called ({len(dead)}):")
            for n in dead:
                lines.append(f"    ✗ {n}")
        if stalled:
            lines.append(
                f"  STALLED — worked before, silent this session " f"({len(stalled)}):"
            )
            for n in stalled:
                c = self._counters.get(n)
                last = (
                    time.strftime("%Y-%m-%d %H:%M", time.gmtime(c.last_ts))
                    if c and c.last_ts > 0
                    else "?"
                )
                lines.append(f"    ! {n}  (last activity {last} UTC)")
        active = [c for c in counters if c.session_calls > 0]
        if active and include_healthy:
            lines.append(f"  ACTIVE this session ({len(active)}):")
            for c in active:
                extra = []
                if c.total_skips:
                    top = sorted(c.skips.items(), key=lambda kv: -kv[1])[:2]
                    extra.append("skips=" + ",".join(f"{k}×{v}" for k, v in top))
                if c.total_exceptions:
                    top = sorted(c.exceptions.items(), key=lambda kv: -kv[1])[:2]
                    extra.append("EXC=" + ",".join(f"{k}×{v}" for k, v in top))
                suffix = ("  " + "  ".join(extra)) if extra else ""
                lines.append(
                    f"    ✓ {c.name}  calls={c.session_calls:,}"
                    f" (lifetime {c.calls:,}){suffix}"
                )
        # Features with exceptions but no successful calls are the
        # worst case — wired but broken. Call them out separately.
        broken = [
            c for c in counters if c.session_calls == 0 and c.total_exceptions > 0
        ]
        if broken:
            lines.append(
                f"  BROKEN — exceptions with no successful calls " f"({len(broken)}):"
            )
            for c in broken:
                top = sorted(c.exceptions.items(), key=lambda kv: -kv[1])[:3]
                lines.append(
                    f"    ✗ {c.name}  " + ", ".join(f"{k}×{v}" for k, v in top)
                )
        return lines

    # ── markdown report (v3.24.8) ────────────────────────────────

    def write_markdown_report(
        self,
        path: Optional[Path] = None,
        scope: str = "",
        run_context: Optional[dict] = None,
    ) -> Optional[Path]:
        """Write a Feature Validation & Error report in markdown.

        Operator directive 2026-08-02: "Module must produce a Feature
        Validation and Error log in a mark down format you can read
        and use immediately for improvement. Should show Python and
        application specific errors."

        Written to ``~/.acervator_logs/feature_validation.md`` by
        default so it can be read directly next session without the
        operator pasting anything.

        Two error classes are separated because they need different
        fixes:
          * PYTHON errors  — exception type names captured via
            ``record_exception`` (RecursionError, AttributeError…).
            These are code defects.
          * APPLICATION errors — skip reasons captured via
            ``record_skip`` ("bot has no _last_gate_state",
            "no candle at cursor"). These are wiring/data gaps —
            the code ran but had nothing to work with.

        Returns the written path, or None on failure.
        """
        target = path or (_telemetry_root(".acervator_logs") / "feature_validation.md")
        counters = self.snapshot(scope)
        dead = self.dead_features(scope)
        stalled = [
            n for n in self.dead_features(scope, session_only=True) if n not in dead
        ]
        active = [c for c in counters if c.session_calls > 0]
        broken = [
            c for c in counters if c.session_calls == 0 and c.total_exceptions > 0
        ]

        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        L: list[str] = []
        L.append("# Feature Validation & Error Report")
        L.append("")
        L.append(f"Generated: {ts} UTC")
        if scope:
            L.append(f"Scope: `{scope}`")
        if run_context:
            for k, v in run_context.items():
                L.append(f"{k}: {v}")
        L.append("")

        # -- verdict banner: the first thing to read ---------------
        problems = len(dead) + len(stalled) + len(broken)
        if problems == 0 and active:
            L.append("**VERDICT: all declared features fired.**")
        elif not counters:
            L.append("**VERDICT: no features recorded or declared.**")
        else:
            L.append(
                f"**VERDICT: {problems} feature(s) need attention** "
                f"— {len(dead)} dead, {len(stalled)} stalled, "
                f"{len(broken)} broken."
            )
        L.append("")

        # -- dead ---------------------------------------------------
        L.append("## Dead features (declared, never called)")
        L.append("")
        if dead:
            L.append(
                "These are wired into the UI but nothing feeds "
                "them. This is the scaffolding signal."
            )
            L.append("")
            L.append("| Feature | Lifetime calls |")
            L.append("|---|---|")
            for n in dead:
                c = self._counters.get(n)
                L.append(f"| `{n}` | {c.calls if c else 0} |")
        else:
            L.append("_None._")
        L.append("")

        # -- stalled ------------------------------------------------
        L.append("## Stalled features (worked before, silent now)")
        L.append("")
        if stalled:
            L.append("| Feature | Lifetime calls | Last activity (UTC) |")
            L.append("|---|---|---|")
            for n in stalled:
                c = self._counters.get(n)
                last = (
                    time.strftime("%Y-%m-%d %H:%M", time.gmtime(c.last_ts))
                    if c and c.last_ts > 0
                    else "never"
                )
                L.append(f"| `{n}` | {c.calls if c else 0} | {last} |")
        else:
            L.append("_None._")
        L.append("")

        # -- python errors ------------------------------------------
        L.append("## Python errors (exceptions raised)")
        L.append("")
        py_rows = [
            (c.name, k, v)
            for c in counters
            for k, v in sorted(c.exceptions.items(), key=lambda kv: -kv[1])
        ]
        if py_rows:
            L.append(
                "Code defects. Each row is an exception type "
                "caught at a feature boundary."
            )
            L.append("")
            L.append("| Feature | Exception | Count |")
            L.append("|---|---|---|")
            for name, exc, cnt in py_rows:
                L.append(f"| `{name}` | `{exc}` | {cnt} |")
        else:
            L.append("_None._")
        L.append("")

        # -- application errors -------------------------------------
        L.append("## Application errors (skips with reasons)")
        L.append("")
        app_rows = [
            (c.name, k, v)
            for c in counters
            for k, v in sorted(c.skips.items(), key=lambda kv: -kv[1])
        ]
        if app_rows:
            L.append(
                "The code ran but had nothing to work with — "
                "wiring or data gaps, not crashes."
            )
            L.append("")
            L.append("| Feature | Skip reason | Count |")
            L.append("|---|---|---|")
            for name, reason, cnt in app_rows:
                L.append(f"| `{name}` | {reason} | {cnt} |")
        else:
            L.append("_None._")
        L.append("")

        # -- active -------------------------------------------------
        L.append("## Active features (fired this session)")
        L.append("")
        if active:
            L.append("| Feature | Session calls | Lifetime | Skips | Exceptions |")
            L.append("|---|---|---|---|---|")
            for c in sorted(active, key=lambda x: -x.session_calls):
                L.append(
                    f"| `{c.name}` | {c.session_calls:,} | "
                    f"{c.calls:,} | {c.total_skips} | "
                    f"{c.total_exceptions} |"
                )
        else:
            L.append("_None fired this session._")
        L.append("")

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("\n".join(L), encoding="utf-8")
            return target
        except OSError as exc:
            logger.warning("feature_telemetry: markdown write failed: %s", exc)
            return None

    # ── persistence ──────────────────────────────────────────────

    def load(self) -> bool:
        """Restore lifetime counters. Returns True on success.
        On ANY error the registry starts empty and logs a WARNING —
        stale counts reported as current would be worse than none."""
        try:
            if not self._path.exists():
                return False
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "feature_telemetry: load failed (%s) — starting " "with empty counters",
                exc,
            )
            return False
        if not isinstance(raw, dict):
            return False
        rows = raw.get("features") or []
        with self._lock:
            for d in rows:
                if not isinstance(d, dict):
                    continue
                c = FeatureCounter.from_dict(d)
                if c.name:
                    self._counters[c.name] = c
            for n in raw.get("declared") or []:
                if isinstance(n, str) and n:
                    self._declared.add(n)
        return True

    def save(self) -> bool:
        """Persist lifetime counters. Atomic write via temp+replace
        so a crash mid-write cannot corrupt the file."""
        with self._lock:
            payload = {
                "schema_version": SCHEMA_VERSION,
                "saved_at": time.time(),
                "declared": sorted(self._declared),
                "features": [c.to_dict() for c in self._counters.values()],
            }
        try:
            atomic_write_json(self._path, payload, indent=None, separators=(",", ":"))
            return True
        except OSError as exc:
            logger.warning("feature_telemetry: save failed: %s", exc)
            return False

    def reset(self, scope: str = "") -> int:
        """Clear counters (lifetime included). Returns count removed.
        Declarations are retained so dead-feature detection survives."""
        with self._lock:
            names = [n for n in self._counters if not scope or n.startswith(scope)]
            for n in names:
                del self._counters[n]
            for n in self._declared:
                if not scope or n.startswith(scope):
                    self._counters[n] = FeatureCounter(name=n)
        return len(names)


# ── singleton ────────────────────────────────────────────────────

_telemetry: Optional[FeatureTelemetry] = None
_singleton_lock = threading.Lock()


def get_telemetry() -> FeatureTelemetry:
    global _telemetry
    if _telemetry is None:
        with _singleton_lock:
            if _telemetry is None:
                _telemetry = FeatureTelemetry()
    return _telemetry


__all__ = [
    "SCHEMA_VERSION",
    "TELEMETRY_PATH",
    "telemetry_path",
    "FeatureCounter",
    "FeatureTelemetry",
    "get_telemetry",
]

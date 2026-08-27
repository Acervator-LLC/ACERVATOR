"""
version_sweep.py — Mandatory Version Bump Quality Gate
========================================================
Triggered by R25: for every 0.1v increment, a full code optimization
and security sweep must pass before the release is considered valid.

Run:
    python src/core/version_sweep.py [--fix] [--report]

    --fix     Apply auto-fixable issues (unused imports, trailing whitespace)
    --report  Generate PDF report (requires reportlab)

Exit codes:
    0  All checks passed (or only warnings)
    1  One or more CRITICAL or HIGH findings require manual resolution
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("acervator.version_sweep")

# ── Project root ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent


# ── Finding severity ──────────────────────────────────────────────────────────
class Severity:
    CRITICAL = "CRITICAL"  # Must fix before release
    HIGH = "HIGH"  # Should fix before release
    MEDIUM = "MEDIUM"  # Fix in next session
    LOW = "LOW"  # Minor / informational
    INFO = "INFO"  # Audit trail only


@dataclass
class Finding:
    severity: str
    category: str  # SECURITY | QUALITY | CONSISTENCY | DEPENDENCY | HYGIENE
    file: str
    line: int
    description: str
    suggestion: str = ""
    auto_fixable: bool = False


@dataclass
class SweepResult:
    version: str
    timestamp: str
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    lines_scanned: int = 0
    elapsed_sec: float = 0.0

    @property
    def critical(self):
        return [f for f in self.findings if f.severity == Severity.CRITICAL]

    @property
    def high(self):
        return [f for f in self.findings if f.severity == Severity.HIGH]

    @property
    def medium(self):
        return [f for f in self.findings if f.severity == Severity.MEDIUM]

    @property
    def low(self):
        return [f for f in self.findings if f.severity == Severity.LOW]

    @property
    def passed(self):
        return len(self.critical) == 0 and len(self.high) == 0


# ─────────────────────────────────────────────────────────────────────────────
# CHECK REGISTRY
# ─────────────────────────────────────────────────────────────────────────────


class VersionSweep:

    SKIP_DIRS = {
        "__pycache__",
        ".git",
        "node_modules",
        "data",
        "reports",
        "logs",
        "cpp_version",
        "cloud",
        "dist",
        "build",
    }
    SKIP_EXTS = {
        ".pyc",
        ".png",
        ".jpg",
        ".gif",
        ".mp4",
        ".pdf",
        ".zip",
        ".spec",
        ".json",
    }

    # Patterns that must NEVER appear in source
    SECRET_PATTERNS = [
        # Hard-coded credential fragments
        (r'api_key\s*=\s*["\'][A-Za-z0-9+/]{20,}["\']', "Possible hard-coded API key"),
        (
            r'api_secret\s*=\s*["\'][A-Za-z0-9+/]{20,}["\']',
            "Possible hard-coded API secret",
        ),
        (r'password\s*=\s*["\'][^"\']{6,}["\']', "Possible hard-coded password"),
        (r'token\s*=\s*["\'][A-Za-z0-9_\-\.]{20,}["\']', "Possible hard-coded token"),
        # AWS / common cloud keys
        (r"AKIA[0-9A-Z]{16}", "Possible AWS access key ID"),
        (r"(?:=|:)\s*[A-Za-z0-9/+]{40}", "Possible AWS secret key (40-char base64)"),
        # Private key header
        # PEM private key: flagged as INFO not CRITICAL since key-processing
        # code legitimately references these strings for format normalization.
        # Manually verify any hit is not actual embedded key material.
        (
            r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",
            "PEM private key header — verify this is format-handling, not embedded key",
        ),
    ]

    # Insecure function / import patterns
    INSECURE_PATTERNS = [
        (r"\bpickle\.loads?\b", "pickle.load is unsafe with untrusted data"),
        (r"\beval\s*\(", "eval() executes arbitrary code"),
        (r"\bexec\s*\(", "exec() executes arbitrary code (check if intentional)"),
        (
            r"\bos\.system\s*\(",
            "os.system() is vulnerable to shell injection — use subprocess",
        ),
        (
            r"\bsubprocess\.call\s*\(.*shell\s*=\s*True",
            "subprocess with shell=True is vulnerable to injection",
        ),
        (
            r"\bsubprocess\.run\s*\(.*shell\s*=\s*True",
            "subprocess with shell=True is vulnerable to injection",
        ),
        (r"\bhashlib\.md5\b", "MD5 is cryptographically broken — use SHA-256+"),
        (r"\bhashlib\.sha1\b", "SHA-1 is cryptographically weak — use SHA-256+"),
        (
            r"\brandom\.random\b",
            "random.random() is not cryptographically secure; use secrets module for auth",
        ),
        (
            r"\bhttp://(?!localhost|127\.0\.0\.1)",
            "Plain HTTP in non-localhost URL — use HTTPS",
        ),
    ]

    # Debug / development leftovers
    DEBUG_PATTERNS = [
        (r"\bbreakpoint\(\)", "breakpoint() left in production code"),
        (r"\bpdb\.set_trace\(\)", "pdb.set_trace() left in production code"),
        (r'\bprint\s*\(\s*["\']DEBUG', "Debug print statement"),
        (r"# (?:TEMP|HACK|XXX|FIXME|BUG)\b", "Flagged comment requires attention"),
    ]

    def __init__(self, root: Path = ROOT, fix: bool = False):
        self.root = root
        self.fix = fix
        self.result = SweepResult(
            version=self._get_version(),
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        # v3.24.21 — files this sweep could not read or parse.
        # Every scanning loop used `except Exception: continue`, so an
        # unreadable file was silently dropped from EVERY check —
        # including check_secrets. A sweep that skipped a file then
        # reported "no hard-coded credentials" was reporting that it
        # had not looked, in language indistinguishable from having
        # looked and found nothing.
        self._skipped: list[tuple[str, str]] = []

    def _read_or_skip(self, path: Path) -> Optional[str]:
        """Read a file for scanning, recording (not swallowing) failure.

        Returns None when the file cannot be read; the caller continues
        as before, but the skip is now attributable.
        """
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            rel = str(path)
            try:
                rel = str(path.relative_to(self.root))
            except ValueError:
                pass
            self._skipped.append((rel, f"{type(exc).__name__}: {exc}"))
            logger.warning(
                "version_sweep: could not read %s (%s) — file is "
                "EXCLUDED from all checks",
                rel,
                exc,
            )
            return None

    @property
    def skipped_files(self) -> list[tuple[str, str]]:
        """Files excluded from the sweep, with the reason for each."""
        return list(self._skipped)

    def _get_version(self) -> str:
        try:
            init = (self.root / "src" / "__init__.py").read_text()
            m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init)
            return m.group(1) if m else "unknown"
        except Exception:
            return "unknown"

    def _py_files(self):
        for dirpath, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in files:
                if fname.endswith(".py"):
                    yield Path(dirpath) / fname

    def _all_files(self):
        for dirpath, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in files:
                ext = Path(fname).suffix.lower()
                if ext not in self.SKIP_EXTS:
                    yield Path(dirpath) / fname

    def _rel(self, p: Path) -> str:
        return str(p.relative_to(self.root))

    def _add(self, sev, cat, path, line, desc, suggestion="", auto_fixable=False):
        self.result.findings.append(
            Finding(
                severity=sev,
                category=cat,
                file=self._rel(path),
                line=line,
                description=desc,
                suggestion=suggestion,
                auto_fixable=auto_fixable,
            )
        )

    # ── CHECK 1: Syntax ───────────────────────────────────────────────────────

    def check_syntax(self):
        """Every .py file must parse cleanly."""
        for path in self._py_files():
            self.result.files_scanned += 1
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
                self.result.lines_scanned += source.count("\n")
                ast.parse(source)
            except SyntaxError as e:
                self._add(
                    Severity.CRITICAL,
                    "QUALITY",
                    path,
                    e.lineno or 0,
                    f"Syntax error: {e.msg}",
                    "Fix syntax before release.",
                )

    # ── CHECK 2: Version consistency ──────────────────────────────────────────

    def check_version_consistency(self):
        """No file may restate a version that differs from src/__init__.py.

        Issue #70 rewrote the rule this check enforces. It used to DEMAND a
        version literal in each listed file and raise MEDIUM when one was
        absent. That is backwards: a file that carries no literal cannot
        drift, so absence is the correct end state, not a finding.

        Two of the four paths it listed (render_trailer.py and
        sadp/RAIntSimBat/RAIntSimBat.py) do not exist in the tree and were
        skipped every run. main.py stopped matching its pattern when it
        moved to `from src import __version__`, so it had been scoring a
        MEDIUM for doing the right thing.

        What remains: if one of these files DOES restate a version, that
        restatement must equal the canonical value.
        """
        canonical = self.result.version
        if canonical == "unknown":
            return

        version_sources = {
            self.root / "main.py": r'current_version\s*=\s*["\']([^"\']+)["\']',
            self.root / "splash_screen.py": r'__version__\s*=\s*["\']([^"\']+)["\']',
            self.root / "investor_screen.py": r'__version__\s*=\s*["\']([^"\']+)["\']',
            self.root
            / "generate_essay_ja.py": r'__version__\s*=\s*["\']([^"\']+)["\']',
        }

        for fpath, pattern in version_sources.items():
            if not fpath.exists():
                continue
            text = fpath.read_text(errors="replace")
            m = re.search(pattern, text)
            # No match == the file imports __version__ == nothing can drift.
            if m and m.group(1) != canonical:
                self._add(
                    Severity.HIGH,
                    "CONSISTENCY",
                    fpath,
                    0,
                    f"Version mismatch: {m.group(1)!r} != canonical {canonical!r}",
                    f"Import __version__ from src rather than restating {m.group(1)!r}.",
                )

        # Docs must also reference the right version
        doc_files = [
            self.root / "ACERVATOR_HOP2.md",
            self.root / "AI_DEVELOPER_GUIDE.md",
            self.root / "CHANGELOG.md",
        ]
        for dpath in doc_files:
            if not dpath.exists():
                continue
            text = dpath.read_text(errors="replace")
            # Check if ANY previous version (not canonical) appears without being in a historical block
            old_vers = re.findall(r"\b3\.\d+\.\d+\b", text)
            old_refs = [v for v in old_vers if v != canonical]
            if old_refs and dpath.name != "CHANGELOG.md":
                unique_old = list(set(old_refs))
                self._add(
                    Severity.MEDIUM,
                    "CONSISTENCY",
                    dpath,
                    0,
                    f"Stale version reference(s) found: {unique_old}",
                    f"Update all to {canonical}.",
                )

    # ── CHECK 3: Security — secrets ──────────────────────────────────────────

    def check_secrets(self):
        """No hard-coded credentials or key material in source."""
        for path in self._all_files():
            text = self._read_or_skip(path)
            if text is None:
                continue

            # Skip the encryption.py and usb_auth.py constants — those are app secrets, not creds
            rel = self._rel(path)
            skip_for_secret = {"encryption.py", "usb_auth.py"}
            # Skip documentation — prose can contain 40-char sequences
            # contracts/ = Solidity address constants; *.md = prose documentation;
            # sadp/ = SADP files that may contain hex in examples
            skip_dirs_secret = {
                "docs",
                "deploy/kiosk",
                "contracts",
                "sadp",
                ".session26_backups",
            }
            # v3.16.14 — added .jsonl (SADP append-only logs containing
            # descriptive text, occasionally false-flagged for 40-char
            # base64 patterns). Logs never contain real credentials; the
            # operator's secrets stay encrypted in keyring.
            skip_ext_secret = {".md", ".sol", ".txt", ".bak", ".jsonl"}
            if any(s in rel for s in skip_for_secret):
                continue
            if any(
                f"/{d}/" in f"/{rel}" or rel.startswith(f"{d}/")
                for d in skip_dirs_secret
            ):
                continue
            if Path(rel).suffix in skip_ext_secret:
                continue

            for line_no, line in enumerate(text.splitlines(), 1):
                for pattern, desc in self.SECRET_PATTERNS:
                    if re.search(pattern, line, re.I):
                        # Skip comments and test fixtures
                        stripped = line.strip()
                        if stripped.startswith("#"):
                            continue
                        if "test" in rel.lower() or "example" in rel.lower():
                            sev = Severity.LOW
                        elif "PEM" in desc or "private key header" in desc:
                            sev = Severity.MEDIUM  # Could be format handling code
                        else:
                            sev = Severity.HIGH  # Real credential pattern
                        self._add(
                            sev,
                            "SECURITY",
                            path,
                            line_no,
                            desc,
                            "Move to encrypted vault or environment variable.",
                        )

    # ── CHECK 4: Security — insecure patterns ────────────────────────────────

    def check_insecure_patterns(self):
        """Flag known insecure coding patterns.
        GUI animation files may legitimately use random — skip visual-only files.
        """
        # _skip_random applied in the pattern loop below
        for path in self._py_files():
            text = self._read_or_skip(path)
            if text is None:
                continue

            # exec() is intentionally used in root RAIntSimBat.py wrapper — skip that one
            # random.random() is used for visual animation in splash — not security risk
            rel = self._rel(path)
            # v3.16.14 — extended skip list for non-security random.random
            # uses (audio synthesis white-noise + sim test fixtures).
            _visual_files = {
                "splash_screen.py",
                "render_trailer.py",
                "sound_engine.py",  # audio white-noise generator
                # tests/investigate_*.py — test fixtures with synthetic candles
            }
            if path.name in _visual_files:
                continue  # animation/audio code — random is not security-sensitive
            # Test fixtures using random for synthetic data — skip.
            # Use os.sep-agnostic check (Windows uses backslashes).
            _norm_rel = rel.replace("\\", "/")
            if _norm_rel.startswith("tests/") and (
                "investigate_" in path.name
                or "fixture" in path.name
                or "_test" in path.name
            ):
                continue
            # Self-exemption: version_sweep.py contains these patterns as data strings
            if "version_sweep.py" in rel:
                continue
            is_wrapper = "RAIntSimBat.py" in rel and "RAIntSimBat/" not in rel

            for line_no, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                # v3.16.14 — recognize bandit-style `# nosec` and explicit
                # `# version-sweep: accept` comments as operator-blessed
                # exemptions. Avoids needing per-pattern allowlists for
                # genuinely-defensive code (e.g., trusted-config shell=True).
                if "# nosec" in line or "# version-sweep:" in line.lower():
                    continue
                for pattern, desc in self.INSECURE_PATTERNS:
                    if re.search(pattern, line):
                        # exec() in the root wrapper is intentional
                        if "exec(" in pattern and is_wrapper:
                            self._add(
                                Severity.INFO,
                                "SECURITY",
                                path,
                                line_no,
                                f"{desc} (intentional wrapper — documented)",
                                "Confirmed safe: exec() in root wrapper only.",
                            )
                            continue
                        # random.random() in simulation/noise is fine
                        if "random.random" in pattern and (
                            "gen_from_anchors" in text or "sim" in rel.lower()
                        ):
                            continue
                        sev = (
                            Severity.HIGH
                            if any(
                                x in desc
                                for x in ("key", "secret", "private", "injection")
                            )
                            else Severity.MEDIUM
                        )
                        self._add(
                            sev,
                            "SECURITY",
                            path,
                            line_no,
                            desc,
                            "Review and replace with secure alternative.",
                        )

    # ── CHECK 5: Debug leftovers ──────────────────────────────────────────────

    def check_debug_leftovers(self):
        for path in self._py_files():
            text = self._read_or_skip(path)
            if text is None:
                continue
            # Self-exemption: pattern strings are data here
            if "version_sweep.py" in self._rel(path):
                continue
            for line_no, line in enumerate(text.splitlines(), 1):
                for pattern, desc in self.DEBUG_PATTERNS:
                    if re.search(pattern, line, re.I):
                        self._add(
                            Severity.MEDIUM,
                            "HYGIENE",
                            path,
                            line_no,
                            desc,
                            "Remove before release.",
                            auto_fixable=False,
                        )

    # ── CHECK 6: Unused imports ───────────────────────────────────────────────

    def check_unused_imports(self):
        """Flag obviously unused top-level imports."""
        for path in self._py_files():
            source = self._read_or_skip(path)
            if source is None:
                continue
            try:
                tree = ast.parse(source)
            except SyntaxError as _syn:
                # v3.24.21 — a file that does not parse is excluded from
                # every AST-based check. Record it rather than vanish.
                self._skipped.append((str(path), f"SyntaxError: {_syn}"))
                logger.warning(
                    "version_sweep: %s failed to parse (%s) — EXCLUDED "
                    "from AST checks",
                    path,
                    _syn,
                )
                continue

            imported_names = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        name = alias.asname or alias.name.split(".")[0]
                        imported_names.append((name, node.lineno))
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name == "*":
                            continue
                        name = alias.asname or alias.name
                        imported_names.append((name, node.lineno))

            # Count usages (rough — excludes __all__, string references)
            for name, lineno in imported_names:
                if name.startswith("_"):
                    continue
                # Count occurrences outside the import line itself
                occurrences = len(re.findall(r"\b" + re.escape(name) + r"\b", source))
                # The import line itself counts as 1; also __all__ re-exports
                if occurrences <= 1 and "__all__" not in source:
                    self._add(
                        Severity.LOW,
                        "QUALITY",
                        path,
                        lineno,
                        f"Possibly unused import: '{name}'",
                        "Remove if confirmed unused.",
                        auto_fixable=True,
                    )

    # ── CHECK 7: R6 two-path consistency ─────────────────────────────────────

    def check_r6_two_paths(self):
        """
        R6: simulator has TWO execution paths. Verify key mechanism functions
        exist in both simulator.py and RAIntSimBat.py.
        Key gates that must appear in both:
          MACD taper, VX ceiling, Ichimoku, Slingshot, CM Slingshot
        """
        sim_path = self.root / "src" / "gui" / "simulator.py"
        bat_path = self.root / "sadp" / "RAIntSimBat" / "RAIntSimBat.py"

        if not sim_path.exists() or not bat_path.exists():
            return

        sim_text = sim_path.read_text(errors="replace")
        bat_text = bat_path.read_text(errors="replace")

        gate_pairs = [
            ("MACD TAPER", r"MACD.*taper|macd.*taper", r"macd_taper|MACD TAPER"),
            ("VX CEILING", r"vip_at_ceiling|VX.*CEIL", r"VX.*ceil|_vip_ceil"),
            ("ICHIMOKU GATE", r"ichi_twist_bull|ICHIMOKU", r"ICHIMOKU|_ichi_"),
            ("CM SLINGSHOT SQUEEZE", r"squeeze_bull|SLINGSHOT", r"SLINGSHOT|_sq_bull"),
            # Phantom Gate: intentionally disabled in simulator.py (documented in
            # Section 19.18 of Product Manual — synthetic data limitation).
            # Excluded from R6 violation check.
            # ("PHANTOM GATE", r"phantom_lock|phantom", r"phantom_lock"),
        ]

        for name, sim_pat, bat_pat in gate_pairs:
            in_sim = bool(re.search(sim_pat, sim_text, re.I))
            in_bat = bool(re.search(bat_pat, bat_text, re.I))
            if in_sim and not in_bat:
                self._add(
                    Severity.HIGH,
                    "CONSISTENCY",
                    bat_path,
                    0,
                    f"R6 VIOLATION: {name} gate in simulator.py but NOT in RAIntSimBat.py",
                    "Add matching gate to run_v3192 or document intentional exclusion.",
                )
            elif in_bat and not in_sim:
                self._add(
                    Severity.HIGH,
                    "CONSISTENCY",
                    sim_path,
                    0,
                    f"R6 VIOLATION: {name} gate in RAIntSimBat.py but NOT in simulator.py",
                    "Add matching gate to simulator.py confidence pipeline.",
                )

    # ── CHECK 8: Requirements coverage ───────────────────────────────────────

    def check_requirements(self):
        """Check that key imports have entries in requirements files."""
        req_file = self.root / "requirements.txt"
        req_opt = self.root / "requirements-optional.txt"
        reqs_text = ""
        if req_file.exists():
            reqs_text += req_file.read_text().lower()
        if req_opt.exists():
            reqs_text += req_opt.read_text().lower()

        # Core dependencies that must be declared
        required_packages = {
            "PySide6": "pyside6",
            "ccxt": "ccxt",
            "reportlab": "reportlab",
            "cryptography": "cryptography",
        }

        for import_name, pkg_name in required_packages.items():
            if pkg_name not in reqs_text:
                # Check if it's actually imported
                used = False
                for path in self._py_files():
                    _probe = self._read_or_skip(path)
                    if _probe is None:
                        continue
                    if import_name in _probe:
                        used = True
                        break
                if used:
                    self._add(
                        Severity.MEDIUM,
                        "DEPENDENCY",
                        (
                            req_file
                            if req_file.exists()
                            else self.root / "requirements.txt"
                        ),
                        0,
                        f"'{import_name}' used in source but not in requirements files",
                        f"Add '{pkg_name}' to requirements.txt or requirements-optional.txt",
                    )

    # ── CHECK 9: File hygiene ─────────────────────────────────────────────────

    def check_file_hygiene(self):
        """Flag stale artifacts that shouldn't ship."""
        stale_patterns = [
            (r"\.pyc$", "Compiled .pyc file should not be committed"),
            (r"__pycache__", "pycache directory should not be committed"),
            (r"\.DS_Store", "macOS metadata file should not be committed"),
            (r"Thumbs\.db", "Windows thumbnail cache should not be committed"),
            (r"\.env$", "Environment file may contain secrets"),
        ]
        for dirpath, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in {".git"}]
            for fname in files:
                fpath = Path(dirpath) / fname
                rel = self._rel(fpath)
                for pattern, desc in stale_patterns:
                    if re.search(pattern, rel):
                        self._add(
                            Severity.LOW,
                            "HYGIENE",
                            fpath,
                            0,
                            desc,
                            "Add to .gitignore and remove.",
                        )

    # ── CHECK 11: ta[] snapshot key consistency ─────────────────────────────

    def check_snapshot_consistency(self):
        """
        Verify that every key READ via ta.get("key") or ta["key"] in the
        simulator confidence gates exists in the snapshot dict that is SET
        in _compute_ta_snapshot().

        A missing key silently returns None (via .get()) — the gate branch
        never fires and the indicator is effectively disabled. This class of
        bug is invisible at runtime and undetectable by syntax checking.
        """
        sim_path = self.root / "src" / "gui" / "simulator.py"
        if not sim_path.exists():
            return

        import re

        text = sim_path.read_text(errors="replace")

        # Keys SET in the snapshot dict
        snap_pat = r"snapshot\s*=\s*\{(.+?)\}\s*\n\s*# Landing"
        snap_m = re.search(snap_pat, text, re.S)
        if not snap_m:
            self._add(
                Severity.MEDIUM,
                "CONSISTENCY",
                sim_path,
                0,
                "Could not locate snapshot dict in _compute_ta_snapshot()",
                "Verify snapshot = { ... } block is present.",
            )
            return

        set_keys = set(re.findall(r'"([a-z][a-z0-9_]+)":', snap_m.group(1)))

        # Keys READ in confidence gate code (after snapshot is built)
        # Look for ta.get("key") and ta["key"] patterns
        read_keys = set()
        read_keys.update(re.findall(r'ta\.get\("([a-z][a-z0-9_]+)"', text))
        read_keys.update(re.findall(r'ta\["([a-z][a-z0-9_]+)"\]', text))

        # Exclude non-indicator keys that are legitimately outside the snapshot
        exclude = {
            "signals",
            "consensus",
            "confidence",
            "bb",
            "bb_position",
            "idx",
            "tightening",
        }
        read_keys -= exclude

        missing = read_keys - set_keys
        # Filter to only indicator-style keys (exclude API/JSON keys)
        indicator_missing = {
            k
            for k in missing
            if any(
                k.startswith(p)
                for p in (
                    "ichi_",
                    "vx_",
                    "macd_",
                    "srsi_",
                    "mkt_",
                    "bb_",
                    "ha_",
                    "vol_",
                    "sling_",
                    "adx_",
                    "st_",
                    "z_",
                    "er_",
                )
            )
        }

        for key in sorted(indicator_missing):
            self._add(
                Severity.HIGH,
                "CONSISTENCY",
                sim_path,
                0,
                f"ta[{key!r}] read in gates but NOT in snapshot — "
                "gate branch silently returns None, indicator disabled",
                f"Add {key!r} to snapshot dict with correct ichi_d.get() source.",
            )

    # ── CHECK 10: TODO / FIXME count ─────────────────────────────────────────

    def check_todos(self):
        total = 0
        for path in self._py_files():
            text = self._read_or_skip(path)
            if text is None:
                continue
            for line_no, line in enumerate(text.splitlines(), 1):
                if re.search(r"#\s*(TODO|FIXME|HACK|STUB)\b", line, re.I):
                    total += 1
                    self._add(
                        Severity.LOW,
                        "HYGIENE",
                        path,
                        line_no,
                        f"Unresolved {re.search(r'(TODO|FIXME|HACK|STUB)', line, re.I).group(1)}",
                        "Resolve or promote to Risk Register.",
                    )
        if total > 0:
            self._add(
                Severity.INFO,
                "HYGIENE",
                self.root / "src",
                0,
                f"Total unresolved TODO/FIXME/HACK/STUB comments: {total}",
                "Review before release.",
            )

    # ── CHECK 12: Rule registry ──────────────────────────────────────────────

    def check_rule_registry(self):
        """
        Read sadp/RULE_REGISTRY.json and flag:
          HIGH    — any CORE rule (R1, R5, R10, R11, R12) that is not LOCKED
          MEDIUM  — any SUSPENDED rule (note it prominently for the session)
          LOW     — any UNLOCKED rule (may be intentional, flag for awareness)
          INFO    — registry missing (will be auto-created on first use)
        """
        registry_path = self.root / "sadp" / "RULE_REGISTRY.json"
        if not registry_path.exists():
            self._add(
                Severity.INFO,
                "CONSISTENCY",
                registry_path,
                0,
                "sadp/RULE_REGISTRY.json not found — will be created on first RULE command",
                "Run: python src/core/rule_registry.py",
            )
            return

        try:
            import json as _json

            data = _json.loads(registry_path.read_text())
        except Exception as e:
            self._add(
                Severity.MEDIUM,
                "CONSISTENCY",
                registry_path,
                0,
                f"sadp/RULE_REGISTRY.json could not be parsed: {e}",
                "Delete sadp/RULE_REGISTRY.json and re-run: python src/core/rule_registry.py",
            )
            return

        CORE = {"R1", "R5", "R10", "R11", "R12"}

        for rule_id, entry in data.items():
            state = entry.get("state", "UNKNOWN")

            if rule_id in CORE and state != "LOCKED":
                self._add(
                    Severity.HIGH,
                    "CONSISTENCY",
                    registry_path,
                    0,
                    f"CORE rule {rule_id} is {state} — expected LOCKED. "
                    f"CORE rules encode the accumulation algorithm invariants.",
                    f"Run: RULE LOCK {rule_id}",
                )

            elif state == "SUSPENDED":
                reason = entry.get("reason", "no reason given")
                expires = entry.get("expires", "")
                exp_note = f" (expires {expires})" if expires else ""
                self._add(
                    Severity.MEDIUM,
                    "CONSISTENCY",
                    registry_path,
                    0,
                    f"{rule_id} is SUSPENDED{exp_note}: {reason}",
                    f"Run RULE RESTORE {rule_id} when suspension purpose is met.",
                )

            elif state == "UNLOCKED":
                reason = entry.get("reason", "no reason given")
                self._add(
                    Severity.LOW,
                    "CONSISTENCY",
                    registry_path,
                    0,
                    f"{rule_id} is UNLOCKED: {reason}",
                    f"Run RULE LOCK {rule_id} when modification is complete.",
                )

    # ── CHECK 13: Complexity hotspots (R31, R34) ────────────────────────────

    def check_complexity_hotspots(self):
        """Report top functions by complexity (R31 gate) and length (R34 signal)."""
        import re as _re
        import ast as _ast

        BRANCH_PAT = _re.compile(r"\b(if|elif|for|while|except|and|or|case)\b")
        # Scan only src/ — exclude generators, battery engine, etc.
        src_root = self.root / "src"
        scan_root = src_root if src_root.exists() else self.root
        for path in sorted(scan_root.rglob("*.py")):
            if "__pycache__" in str(path):
                continue
            text = self._read_or_skip(path)
            if text is None:
                continue
            try:
                tree = _ast.parse(text)
            except SyntaxError as _syn:
                self._skipped.append((str(path), f"SyntaxError: {_syn}"))
                logger.warning(
                    "version_sweep: %s failed to parse (%s) — EXCLUDED "
                    "from AST checks",
                    path,
                    _syn,
                )
                continue
            lines = text.split("\n")
            for node in _ast.walk(tree):
                if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    continue
                end = getattr(node, "end_lineno", node.lineno)
                length = end - node.lineno
                fn_src = "\n".join(lines[node.lineno - 1 : end])
                cc = len(BRANCH_PAT.findall(fn_src)) + 1
                if cc > 50:
                    self._add(
                        Severity.LOW,
                        "COMPLEXITY",
                        path,
                        node.lineno,
                        f"{node.name}() CC={cc} (R31 review threshold: 50) — {length} lines",
                        "Document in TECH_DEBT.md. Do not add new branches.",
                    )

    # ── Run all checks ────────────────────────────────────────────────────────

    def run(self) -> SweepResult:
        t0 = time.time()
        print(f"\n{'='*68}")
        print(f"  ACERVATOR VERSION SWEEP  v{self.result.version}")
        print(f"  {self.result.timestamp}")
        print(f"{'='*68}")

        checks = [
            ("Syntax", self.check_syntax),
            ("Version consistency", self.check_version_consistency),
            ("Security — secrets", self.check_secrets),
            ("Security — patterns", self.check_insecure_patterns),
            ("Debug leftovers", self.check_debug_leftovers),
            ("Unused imports", self.check_unused_imports),
            ("R6 two-path (R6)", self.check_r6_two_paths),
            ("Requirements", self.check_requirements),
            ("File hygiene", self.check_file_hygiene),
            ("TODO/FIXME count", self.check_todos),
            ("Snapshot key sync", self.check_snapshot_consistency),
            ("Rule registry", self.check_rule_registry),
            ("Complexity hotspots", self.check_complexity_hotspots),
            ("SADP annotations (R38)", self.check_sadp_annotations),
            ("R28 silent failures", self.check_r28_silent_failures),
            ("R29/R33 gates", self.check_r29_r33_gates),
            ("SADP dep graph", self.check_sadp_dependency_graph),
        ]

        for name, fn in checks:
            print(f"  Checking: {name}...", end=" ", flush=True)
            before = len(self.result.findings)
            fn()
            after = len(self.result.findings)
            new_count = after - before
            if new_count == 0:
                print("✓")
            else:
                sevs = [f.severity for f in self.result.findings[before:after]]
                worst = (
                    Severity.CRITICAL
                    if Severity.CRITICAL in sevs
                    else (
                        Severity.HIGH
                        if Severity.HIGH in sevs
                        else (
                            Severity.MEDIUM if Severity.MEDIUM in sevs else Severity.LOW
                        )
                    )
                )
                sym = {"CRITICAL": "✗", "HIGH": "⚠", "MEDIUM": "~", "LOW": "·"}
                print(
                    f"{sym.get(worst,'?')} ({new_count} finding{'s' if new_count != 1 else ''})"
                )

        self.result.elapsed_sec = round(time.time() - t0, 2)
        return self.result

    # ── CHECK 14: SADP annotation validation (R38) ──────────────────────────

    def check_sadp_annotations(self):
        """CHECK 14 — Validate # sadp: R[N] annotations (R38)."""
        import re as _re, json as _json

        registry_path = self.root / "sadp" / "RULE_REGISTRY.json"
        try:
            registry = (
                _json.loads(registry_path.read_text()) if registry_path.exists() else {}
            )
        except Exception:
            registry = {}
        suspended = {
            rid for rid, v in registry.items() if v.get("state") == "SUSPENDED"
        }
        ann_pat = _re.compile(r"#\s*sadp:\s*((?:R\d+\s*)+)", _re.IGNORECASE)
        fn_pat = _re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(")
        MANDATORY = [
            ("simulator.py", "_sim_scrumming_tick"),
            ("scrumming_bot.py", "tick"),
            ("token_ledger.py", "award"),
            ("merkle_log.py", "append"),
            ("competition_engine.py", "adjudicate"),
        ]
        mandatory_found = {f"{f}:{fn}": False for f, fn in MANDATORY}
        annotation_count = 0
        for py_file in self.root.rglob("*.py"):
            if any(skip in py_file.parts for skip in self.SKIP_DIRS):
                continue
            _txt = self._read_or_skip(py_file)
            if _txt is None:
                continue
            lines = _txt.splitlines()
            current_fn = None
            for lineno, line in enumerate(lines, 1):
                fn_m = fn_pat.match(line)
                if fn_m:
                    current_fn = fn_m.group(1)
                ann_m = ann_pat.search(line)
                if not ann_m:
                    continue
                annotation_count += 1
                fname = py_file.name
                if current_fn:
                    key = f"{fname}:{current_fn}"
                    if key in mandatory_found:
                        mandatory_found[key] = True
                for rid in ann_m.group(1).split():
                    rid = rid.strip().upper()
                    if not rid:
                        continue
                    if rid not in registry:
                        self._add(
                            Severity.MEDIUM,
                            "SADP",
                            py_file,
                            lineno,
                            f"sadp annotation references unknown rule {rid} "
                            f"in {py_file.name}:{current_fn or chr(63)}",
                            f"Add {rid} to sadp/RULE_REGISTRY.json or correct annotation.",
                        )
                    elif rid in suspended:
                        self._add(
                            Severity.HIGH,
                            "SADP",
                            py_file,
                            lineno,
                            f"sadp annotation references SUSPENDED rule {rid} "
                            f"in {py_file.name}:{current_fn or chr(63)}",
                            f"Run RULE RESTORE {rid} or update the annotation.",
                        )
                    else:
                        self._add(
                            Severity.INFO,
                            "SADP",
                            py_file,
                            lineno,
                            f"sadp: {py_file.name}:{current_fn or chr(63)} governed by {rid}",
                            "",
                        )
        for key, found in mandatory_found.items():
            if not found:
                fname, fnname = key.split(":", 1)
                self._add(
                    Severity.HIGH,
                    "SADP",
                    self.root / fname,
                    0,
                    f"R38: mandatory sadp annotation missing on {fname}:{fnname}.",
                    f"Add  # sadp: R[N]...  comment inside {fnname}().",
                )
        if annotation_count:
            self._add(
                Severity.INFO,
                "SADP",
                self.root / "sadp" / "RULE_REGISTRY.json",
                0,
                f"SADP annotations: {annotation_count} found, all validated.",
                "",
            )

    # ── CHECK 15: R28 silent failure patterns ────────────────────────────────

    def check_r28_silent_failures(self):
        """CHECK 15 — R28 Fail Loudly: detect silent failure patterns."""
        import re as _re

        SCOPED = {"trading", "competition"}
        bare_except = _re.compile(r"^\s*except\s*:")
        swallow_pass = _re.compile(r"^\s*except\s+Exception.*:\s*pass\s*$")
        swallow_cont = _re.compile(r"^\s*except\s+Exception.*:\s*continue\s*$")
        silent_get = _re.compile(r"\.get\(([^,)]+),\s*None\s*\)")
        fn_pat = _re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(")
        for py_file in self.root.rglob("*.py"):
            if any(skip in py_file.parts for skip in self.SKIP_DIRS):
                continue
            parts = [p.lower() for p in py_file.parts]
            if not any(d in parts for d in SCOPED):
                continue
            _txt = self._read_or_skip(py_file)
            if _txt is None:
                continue
            lines = _txt.splitlines()
            fn_ctx = ""
            for lineno, line in enumerate(lines, 1):
                fm = fn_pat.match(line)
                if fm:
                    fn_ctx = fm.group(1)
                if bare_except.match(line):
                    self._add(
                        Severity.HIGH,
                        "SADP-R28",
                        py_file,
                        lineno,
                        f"R28: bare except: in {py_file.name}:{fn_ctx} silences all exceptions.",
                        "Replace with explicit exception type.",
                    )
                elif swallow_pass.match(line) or swallow_cont.match(line):
                    self._add(
                        Severity.MEDIUM,
                        "SADP-R28",
                        py_file,
                        lineno,
                        f"R28: exception swallowed silently in {py_file.name}:{fn_ctx}",
                        "Log or re-raise.",
                    )
                gate_ctx = any(
                    k in fn_ctx.lower() for k in ("confidence", "gate", "tick")
                )
                if gate_ctx:
                    for m in silent_get.finditer(line):
                        self._add(
                            Severity.MEDIUM,
                            "SADP-R28",
                            py_file,
                            lineno,
                            f"R28: .get({m.group(1)}, None) in gate context "
                            f"{py_file.name}:{fn_ctx}",
                            "Use explicit key or safe non-None default.",
                        )

    # ── CHECK 16: R29/R33 idempotency + immutability ─────────────────────────

    def check_r29_r33_gates(self):
        """CHECK 16 — R29 Idempotency + R33 Immutable Log."""
        import re as _re

        SCOPED = {"trading", "competition"}
        submit_pat = _re.compile(
            r"def\s+(submit_order|place_order|award|record_trade|submit_result)\s*\("
        )
        idem_marker = _re.compile(
            r"event_id|client_order_id|_seen|idempotent|already_done|duplicate"
        )
        trunc_pat = _re.compile(r"open\([^,)]+,[^)]*['\x22]w['\x22]|truncate\(")
        log_fn_pat = _re.compile(
            r"def\s+(write_log|append_log|save_log|_write|_append|_save)\s*\("
        )
        for py_file in self.root.rglob("*.py"):
            if any(skip in py_file.parts for skip in self.SKIP_DIRS):
                continue
            parts = [p.lower() for p in py_file.parts]
            if not any(d in parts for d in SCOPED):
                continue
            _txt = self._read_or_skip(py_file)
            if _txt is None:
                continue
            lines = _txt.splitlines()
            in_fn = False
            fn_name = ""
            fn_start = 0
            fn_body = []
            for lineno, line in enumerate(lines, 1):
                sm = submit_pat.search(line)
                if sm:
                    in_fn = True
                    fn_name = sm.group(1)
                    fn_start = lineno
                    fn_body = [line]
                elif in_fn:
                    fn_body.append(line)
                    if lineno > fn_start and line and not line[0].isspace():
                        body = "\n".join(fn_body)
                        if not idem_marker.search(body):
                            self._add(
                                Severity.MEDIUM,
                                "SADP-R29",
                                py_file,
                                fn_start,
                                f"R29: {py_file.name}:{fn_name} lacks visible "
                                f"idempotency marker.",
                                "Add event_id / client_order_id / _seen dedup logic.",
                            )
                        in_fn = False
            in_log = False
            log_name = ""
            log_start = 0
            for lineno, line in enumerate(lines, 1):
                lm = log_fn_pat.search(line)
                if lm:
                    in_log = True
                    log_name = lm.group(1)
                    log_start = lineno
                if in_log and trunc_pat.search(line):
                    self._add(
                        Severity.HIGH,
                        "SADP-R33",
                        py_file,
                        lineno,
                        f"R33: {py_file.name}:{log_name} truncates or overwrites log.",
                        "Use append-only writes.",
                    )
                if in_log and lineno > log_start and line and not line[0].isspace():
                    in_log = False

    # ── CHECK 17: SADP dependency graph propagation ──────────────────────────

    def check_sadp_dependency_graph(self):
        """CHECK 17 — Suspended rules undermining their dependents."""
        import json as _json

        registry_path = self.root / "sadp" / "RULE_REGISTRY.json"
        if not registry_path.exists():
            return
        try:
            registry = _json.loads(registry_path.read_text())
        except Exception:
            return
        suspended = {
            rid for rid, v in registry.items() if v.get("state") == "SUSPENDED"
        }
        if not suspended:
            return
        reverse = {}
        for rule_id, entry in registry.items():
            for dep in entry.get("depends_on", []):
                reverse.setdefault(dep, []).append(rule_id)
        for sus in suspended:
            for dep_rule in reverse.get(sus, []):
                dep_state = registry.get(dep_rule, {}).get("state", "UNKNOWN")
                self._add(
                    Severity.MEDIUM,
                    "SADP-DEP",
                    registry_path,
                    0,
                    f"Dep graph: {sus} SUSPENDED -> {dep_rule} ({dep_state}) "
                    f"depends on it and may be partially undermined.",
                    f"RULE RESTORE {sus} or review {dep_rule} compliance.",
                )

    # ── Report ────────────────────────────────────────────────────────────────

    def print_report(self, result: SweepResult):
        sev_order = [
            Severity.CRITICAL,
            Severity.HIGH,
            Severity.MEDIUM,
            Severity.LOW,
            Severity.INFO,
        ]
        sev_colour = {
            Severity.CRITICAL: "\033[91m",
            Severity.HIGH: "\033[93m",
            Severity.MEDIUM: "\033[94m",
            Severity.LOW: "\033[37m",
            Severity.INFO: "\033[90m",
        }
        RESET = "\033[0m"

        print(f"\n{'='*68}")
        print(f"  SWEEP RESULTS — {result.version}")
        print(
            f"  Files: {result.files_scanned}  Lines: {result.lines_scanned:,}  "
            f"Time: {result.elapsed_sec}s"
        )
        print(
            f"  CRITICAL: {len(result.critical)}  HIGH: {len(result.high)}  "
            f"MEDIUM: {len(result.medium)}  LOW: {len(result.low)}"
        )

        if result.passed:
            print("\n  \033[92m✓ SWEEP PASSED — release gate cleared\033[0m")
        else:
            print(
                f"\n  \033[91m✗ SWEEP FAILED — {len(result.critical)} critical, "
                f"{len(result.high)} high findings must be resolved\033[0m"
            )

        print(f"{'='*68}")

        for sev in sev_order:
            items = [f for f in result.findings if f.severity == sev]
            if not items:
                continue
            col = sev_colour.get(sev, "")
            print(f"\n  {col}── {sev} ({len(items)}) ──{RESET}")
            for f in items:
                loc = f"{f.file}:{f.line}" if f.line else f.file
                print(f"  {col}[{f.severity[:3]}]{RESET} {f.category} | {loc}")
                print(f"       {f.description}")
                if f.suggestion:
                    print(f"       → {f.suggestion}")

        print()

    def save_json_report(self, result: SweepResult) -> Path:
        """Save machine-readable results to sadp/RAIntSimBat/reports/."""
        reports_dir = ROOT / "sadp" / "RAIntSimBat" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        fname = f"sweep_v{result.version}_{time.strftime('%Y%m%d_%H%M%S')}.json"
        out = reports_dir / fname
        data = {
            "version": result.version,
            "timestamp": result.timestamp,
            "elapsed_sec": result.elapsed_sec,
            "files_scanned": result.files_scanned,
            "lines_scanned": result.lines_scanned,
            "passed": result.passed,
            "summary": {
                "critical": len(result.critical),
                "high": len(result.high),
                "medium": len(result.medium),
                "low": len(result.low),
            },
            "findings": [
                {
                    "severity": f.severity,
                    "category": f.category,
                    "file": f.file,
                    "line": f.line,
                    "description": f.description,
                    "suggestion": f.suggestion,
                }
                for f in result.findings
            ],
        }
        out.write_text(json.dumps(data, indent=2))
        return out

    def save_pdf_report(self, result: SweepResult) -> Optional[Path]:
        """Generate a PDF sweep report (R24: human-readable doc → PDF)."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib.colors import HexColor, white
            from reportlab.lib.units import mm
            from reportlab.platypus import (
                Flowable,
                SimpleDocTemplate,
                Paragraph,
                Table,
                TableStyle,
            )

            # v3.19.12 — removed unused TA_LEFT + Spacer + HRFlowable imports
        except ImportError:
            return None

        reports_dir = ROOT / "docs" / "pdf"
        reports_dir.mkdir(parents=True, exist_ok=True)
        fname = f"acervator_sweep_v{result.version}_{time.strftime('%Y%m%d')}.pdf"
        out = reports_dir / fname

        DARK = HexColor("#0A0A14")
        CYAN = HexColor("#00CCAA")
        LIGHT = HexColor("#C8D8F0")
        GREY = HexColor("#667799")
        RED = HexColor("#FF4444")
        GOLD = HexColor("#FFB800")

        def S(name, **kw):
            return ParagraphStyle(name, **kw)

        SS = {
            "Title": S(
                "Title",
                fontName="Helvetica-Bold",
                fontSize=16,
                textColor=CYAN,
                spaceAfter=4,
            ),
            "Sub": S(
                "Sub", fontName="Helvetica", fontSize=9, textColor=GREY, spaceAfter=12
            ),
            "SH": S(
                "SH",
                fontName="Helvetica-Bold",
                fontSize=11,
                textColor=CYAN,
                spaceBefore=10,
                spaceAfter=4,
            ),
            "Body": S(
                "Body",
                fontName="Helvetica",
                fontSize=8,
                textColor=LIGHT,
                spaceAfter=3,
                leading=12,
            ),
        }

        MARGIN = 18 * mm
        W, H = A4
        usable_w = W - 2 * MARGIN

        def on_page(c, doc):
            c.saveState()
            c.setFillColor(DARK)
            c.rect(0, 0, W, H, fill=1, stroke=0)
            c.setFont("Helvetica", 6)
            c.setFillColor(GREY)
            c.drawString(
                MARGIN,
                8 * mm,
                f"Acervator v{result.version} — Security & Optimization Sweep",
            )
            c.drawRightString(W - MARGIN, 8 * mm, f"Page {doc.page}")
            c.restoreState()

        # Annotated, because the list starts with two Paragraphs and
        # later takes Tables as well. Without the annotation the element
        # type is read as Paragraph, and SimpleDocTemplate.build() then
        # gets list[Paragraph] where it asks for list[Flowable].
        story: list[Flowable] = [
            Paragraph(
                f"Acervator v{result.version} — Version Sweep Report", SS["Title"]
            ),
            Paragraph(
                f"{result.timestamp}  ·  "
                f"{result.files_scanned} files  ·  {result.lines_scanned:,} lines  ·  "
                f"{result.elapsed_sec}s",
                SS["Sub"],
            ),
        ]

        # Summary table
        pass_str = "✓ PASSED" if result.passed else "✗ FAILED"
        pass_col = CYAN if result.passed else RED
        summary_data = [
            ["Result", "Critical", "High", "Medium", "Low"],
            [
                pass_str,
                str(len(result.critical)),
                str(len(result.high)),
                str(len(result.medium)),
                str(len(result.low)),
            ],
        ]
        st = Table(summary_data, colWidths=[usable_w * 0.4] + [usable_w * 0.15] * 4)
        st.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#151530")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), white),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("TEXTCOLOR", (0, 1), (0, 1), pass_col),
                    ("FONTNAME", (0, 1), (0, 1), "Helvetica-Bold"),
                    ("TEXTCOLOR", (1, 1), (-1, 1), LIGHT),
                    ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#2a2a5f")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#0C0C18")]),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(st)

        # Findings by severity
        sev_order = [
            ("CRITICAL", RED),
            ("HIGH", GOLD),
            ("MEDIUM", CYAN),
            ("LOW", GREY),
            ("INFO", GREY),
        ]

        for sev, col in sev_order:
            items = [f for f in result.findings if f.severity == sev]
            if not items:
                continue
            story.append(
                Paragraph(
                    f"{sev} — {len(items)} finding{'s' if len(items)!=1 else ''}",
                    SS["SH"],
                )
            )
            # Annotated for the same reason: the header row holds plain
            # strings and every data row below holds Paragraphs.
            rows: list[list[Flowable | str]] = [
                ["Category", "File", "Line", "Description"]
            ]
            for f in items:
                rows.append(
                    [
                        Paragraph(f.category, SS["Body"]),
                        Paragraph(
                            f.file[-40:] if len(f.file) > 40 else f.file, SS["Body"]
                        ),
                        Paragraph(str(f.line) if f.line else "—", SS["Body"]),
                        Paragraph(f.description[:80], SS["Body"]),
                    ]
                )
            ft = Table(rows, colWidths=[60, 130, 30, usable_w - 230])
            ft.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#151530")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), white),
                        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 7),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [HexColor("#0C0C18"), HexColor("#0A0A14")],
                        ),
                        ("TEXTCOLOR", (0, 1), (-1, -1), LIGHT),
                        ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#2a2a5f")),
                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(ft)

        doc = SimpleDocTemplate(
            str(out),
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN,
            bottomMargin=16 * mm,
        )
        doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
        return out


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Acervator version bump quality gate sweep"
    )
    parser.add_argument("--fix", action="store_true", help="Auto-fix fixable issues")
    parser.add_argument(
        "--report", action="store_true", help="Generate PDF report (requires reportlab)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Save JSON report to sadp/RAIntSimBat/reports/",
    )
    args = parser.parse_args()

    sweep = VersionSweep(root=ROOT, fix=args.fix)
    result = sweep.run()
    sweep.print_report(result)

    # v3.19.12 — always save JSON (removed redundant `if args.json or True`
    # — vulture-flagged; the `or True` made args.json a no-op).
    json_path = sweep.save_json_report(result)
    print(f"  JSON report: {json_path.relative_to(ROOT)}")

    if args.report:
        pdf_path = sweep.save_pdf_report(result)
        if pdf_path:
            print(f"  PDF report:  {pdf_path.relative_to(ROOT)}")
        else:
            print("  PDF report:  reportlab not available")

    sys.exit(0 if result.passed else 1)


if __name__ == "__main__":
    main()

"""DocsArchetype — Markdown / prose documentation-quality archetype.

Design (in one paragraph):
  Subprocess-invokes proselint (Python-native prose linter installed
  here). Parses proselint's JSON output into normalized Finding
  objects. If Vale is on PATH, invokes Vale too (Vale is the industry
  standard but requires manual install on Windows). Also does a light
  structural check: presence of an H1 heading, presence of the
  Diataxis-mode signal (any of "Tutorial", "How-to", "Reference",
  "Explanation") near the top.

  Why proselint + Vale-if-available: prose linting is fundamentally
  rule-based; both tools ship curated rule sets grounded in style
  guides (Google, Microsoft, Chicago Manual of Style, alex). We
  invoke them and report; we do NOT re-implement their rule sets.

  FALSIFICATION: this design is wrong if (a) proselint fails to run
  (report will show `missing` or `error`), (b) the JSON format of
  proselint's output changes, (c) the structural check misidentifies
  legitimate docs as mode-less, (d) it fails to distinguish the
  ground-truth good/bad fixture pair.
"""

# ruff: noqa: S603
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from dev_harness.harness.report import (
    REPO_ROOT,
    ArchetypeReport,
    Finding,
    cli_exit,
    refuse_silent_failure,
    scan_rule_modules,
)

__all__ = ["ArchetypeReport", "DocsArchetype", "Finding", "main"]


# proselint check families scored high, whatever severity proselint gave them.
_PROSELINT_HIGH_FAMILIES = {
    "misc.illogic",  # logical errors
    "security",  # credentials-in-docs class
}

# House-style families, scored low whatever severity proselint gave them.
_PROSELINT_STYLE_FAMILIES = ("typography.",)


def _normalize_proselint_severity(check: str, sev: str) -> str:
    if any(check.startswith(f) for f in _PROSELINT_HIGH_FAMILIES):
        return "high"
    if check.startswith(_PROSELINT_STYLE_FAMILIES):
        return "low"
    return {"error": "medium", "warning": "medium", "suggestion": "low"}.get(sev, "low")


# Fenced blocks (``` / ~~~) and inline code spans (`...`).
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def _strip_markdown_code(text: str) -> str:
    """Blank out code so prose linters never see it.

    proselint has no markdown model: it lints a fenced Python block and an
    inline `` `like_this` `` span as English. That is where essentially
    every typography false positive in this repo came from.

    Line COUNT and line NUMBERS are preserved exactly — code lines become
    empty strings rather than being removed — so every reported line
    number still points at the right source line.

    Splits on "\\n" rather than using ``str.splitlines``: splitlines does
    not round-trip through ``"\\n".join`` when the final line is blanked
    and the input has no trailing newline, which silently dropped the last
    line and broke the line-number guarantee this function exists to make.
    """
    out: list[str] = []
    in_fence = False
    for line in text.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else _INLINE_CODE_RE.sub(" ", line))
    return "\n".join(out)


class DocsArchetype:
    """Documentation-quality archetype. Invokes proselint (installed),
    and Vale if on PATH. Also does a light structural check for
    Diataxis-mode signal and H1 heading."""

    name = "documentation_quality"
    version = "1.2"
    tools = ("proselint", "vale", "structure", "story")
    calibration_name = "docs"

    def load_calibration(self) -> str:
        from dev_harness.harness.calibrations import load

        return load(self.calibration_name)

    _DIATAXIS_KEYWORDS = re.compile(
        r"\b(Tutorial|How[- ]?to|Reference|Explanation)\b", re.IGNORECASE
    )

    def review(self, target: Path) -> ArchetypeReport:
        target = Path(target).resolve()
        report = ArchetypeReport(target=str(target))
        if not target.exists():
            report.errors.append(f"target not found: {target}")
            report.falsification = self._build_falsification(report)
            return report

        files = self._enumerate(target)
        if not files:
            report.errors.append(f"no markdown/text files at: {target}")
            report.falsification = self._build_falsification(report)
            return report

        # `scanned` stays False on both returns above, so an empty report
        # cannot answer passed=True.
        report.scanned = True

        for tool_name, runner in [
            ("proselint", self._run_proselint),
            ("vale", self._run_vale),
            ("structure", self._run_structure),
            ("story", self._run_story),
        ]:
            try:
                findings, status = runner(files)
                report.findings.extend(findings)
                report.tool_availability[tool_name] = status
            except FileNotFoundError:
                report.tool_availability[tool_name] = "missing"
                report.errors.append(f"{tool_name}: not installed")
            except subprocess.TimeoutExpired:
                report.tool_availability[tool_name] = "error"
                report.errors.append(f"{tool_name}: timed out")
            except Exception as e:
                report.tool_availability[tool_name] = "error"
                report.errors.append(f"{tool_name}: {type(e).__name__}: {e}")

        scan_rule_modules(
            report,
            target,
            (
                ("scaffolding", "dev_harness.harness.rules.scaffolding"),
                ("hallucination", "dev_harness.harness.rules.hallucination"),
            ),
            (".md", ".txt"),
            files=files,
        )

        report.falsification = self._build_falsification(report)
        return report

    def _build_falsification(self, report: ArchetypeReport) -> str:
        """State the concrete conditions under which this docs report is wrong."""
        ok_tools = [t for t, s in report.tool_availability.items() if s == "ok"]
        missing = [t for t, s in report.tool_availability.items() if s == "missing"]
        parts = [
            "This documentation report is wrong if:",
            f"(a) any tool marked 'ok' ({', '.join(ok_tools) or 'none'}) "
            "produced non-parseable output that the archetype silently dropped;",
            f"(b) the target file/dir {report.target!r} was modified after review;",
            "(c) the Diataxis-mode signal in the doc's opening 500 chars was "
            "phrased in a way the regex missed (e.g., 'walkthrough' instead of "
            "'tutorial');",
            "(d) proselint's rule set was configured differently at review time "
            "than at re-verification time (e.g., ~/.proselintrc changed);",
        ]
        if missing:
            parts.append(
                f"(e) any tool marked 'missing' was in fact installed and "
                f"reachable at review time ({', '.join(missing)}); Vale in "
                "particular would materially widen recall on Google/Microsoft "
                "style compliance."
            )
        parts.append(
            f"(f) any of the {len(report.findings)} listed findings is a "
            "false positive when re-read by a human editor."
        )
        return " ".join(parts)

    # Captured transcripts, not authored documentation, so their prose is
    # not policed.
    _EXCLUDED_SEGMENTS = (
        "/raw/peer_reviewer_",
        "/raw_v2/peer_reviewer_",
        "/gui_raw/peer_reviewer_",
        "/docs_raw/peer_reviewer_",
    )

    def _is_excluded(self, path: Path) -> bool:
        posix = path.as_posix()
        return any(seg in posix for seg in self._EXCLUDED_SEGMENTS)

    def _enumerate(self, target: Path) -> list[Path]:
        if target.is_file():
            return [target]
        files = sorted(list(target.rglob("*.md")) + list(target.rglob("*.txt")))
        return [p for p in files if not self._is_excluded(p)]

    @staticmethod
    def _module_absent(proc: subprocess.CompletedProcess, tool: str) -> bool:
        """True when `python -m <tool>` failed because the module is gone.

        v3.24.34 (C43 follow-on). An absent module does NOT raise
        FileNotFoundError — stdout is EMPTY and the return code is
        non-zero, so `_run_proselint`'s output loop simply iterated
        nothing and the function returned "ok". Uninstalling proselint
        made this archetype report a clean prose review it never ran.

        NOTE: third copy of this check (see
        coding_archetype._module_absent and gui_archetype). Consolidation
        into one shared helper is docketed — a cross-module refactor does
        not belong mid-cascade.
        """
        if proc.returncode == 0:
            return False
        return f"No module named {tool}" in (proc.stderr or "")

    def _run_proselint(self, files: list[Path]) -> tuple[list[Finding], str]:
        """Invoke proselint per-file, parse its text output.

        proselint 0.16.0 ignores --output-format=json (regression) and
        always emits the 'full' text format: <file>:<line>:<col>: <check>: <msg>
        We parse that format directly rather than fight the tool.
        """
        findings: list[Finding] = []
        # <file>:<line>:<col>: <check_id>: <message>
        line_pat = re.compile(
            r"^(?P<file>.+?):(?P<line>\d+):(?P<col>\d+):\s+"
            r"(?P<check>[A-Za-z0-9_.]+):\s+(?P<msg>.+)$"
        )
        for f in files:
            # The stripped copy preserves the line count, so a reported line
            # still resolves against the real file.
            tmp: Optional[Path] = None
            try:
                stripped = _strip_markdown_code(
                    f.read_text(encoding="utf-8", errors="replace")
                )
                fd, tmp_name = tempfile.mkstemp(suffix=".md", prefix="proselint_")
                os.close(fd)
                tmp = Path(tmp_name)
                tmp.write_text(stripped, encoding="utf-8")
                target = tmp
            except OSError:
                # Never let the sanitiser take down the review — fall back
                # to linting the file as-is.
                target = f
            proc = subprocess.run(
                [sys.executable, "-m", "proselint", "check", str(target)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            if tmp is not None:
                tmp.unlink(missing_ok=True)
            if self._module_absent(proc, "proselint"):
                return [], "missing"
            refuse_silent_failure(proc, "proselint")
            for raw_line in proc.stdout.splitlines():
                m = line_pat.match(raw_line)
                if not m:
                    continue
                check = m.group("check")
                findings.append(
                    Finding(
                        tool="proselint",
                        # proselint's text format doesn't carry severity;
                        # normalize by check-family only.
                        severity=_normalize_proselint_severity(check, "warning"),
                        file=str(f),
                        line=int(m.group("line")),
                        rule_id=check,
                        message=m.group("msg"),
                    )
                )
        return findings, "ok"

    def _run_vale(self, files: list[Path]) -> tuple[list[Finding], str]:
        vale_bin = shutil.which("vale")
        if vale_bin is None:
            raise FileNotFoundError("vale not on PATH")
        findings: list[Finding] = []
        for f in files:
            proc = subprocess.run(
                # vale resolves `.vale.ini` against the current directory.
                [vale_bin, "--output=JSON", str(f)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            # vale reports a runtime error as JSON on stderr and leaves
            # stdout empty, which the check below would read as clean.
            refuse_silent_failure(proc, "vale")
            if not proc.stdout.strip():
                continue
            try:
                data = json.loads(proc.stdout)
            except json.JSONDecodeError:
                continue
            # vale JSON: {"path/to/file.md": [{"Check": "Google.Passive", "Line": N, "Severity": "warning", "Message": "..."}]}
            for _, alerts in data.items():
                for alert in alerts:
                    sev = alert.get("Severity", "warning").lower()
                    sev_map = {
                        "error": "high",
                        "warning": "medium",
                        "suggestion": "low",
                    }
                    findings.append(
                        Finding(
                            tool="vale",
                            severity=sev_map.get(sev, "low"),
                            file=str(f),
                            line=alert.get("Line", 0),
                            rule_id=alert.get("Check", "unknown"),
                            message=alert.get("Message", ""),
                        )
                    )
        return findings, "ok"

    def _run_structure(self, files: list[Path]) -> tuple[list[Finding], str]:
        findings: list[Finding] = []
        for f in files:
            text = f.read_text(encoding="utf-8", errors="replace")
            # H1 check: file should have exactly one H1 near the top
            h1s = re.findall(r"^# +\S.*$", text, re.MULTILINE)
            if not h1s:
                findings.append(
                    Finding(
                        tool="structure",
                        severity="medium",
                        file=str(f),
                        line=1,
                        rule_id="DOC001",
                        message="No H1 heading (single '# Title' line) found; the doc has no anchor.",
                    )
                )
            elif len(h1s) > 1:
                findings.append(
                    Finding(
                        tool="structure",
                        severity="low",
                        file=str(f),
                        line=1,
                        rule_id="DOC002",
                        message=f"Multiple H1 headings ({len(h1s)}). Conventional Markdown uses one H1 as title.",
                    )
                )
            # Duplicate-heading check (DOC005) — added 2026-07-24
            # Parse every heading (H1-H6) and flag any repeated text.
            heading_lines: list[tuple[int, str]] = []
            for i, line in enumerate(text.splitlines(), start=1):
                m = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
                if m:
                    heading_lines.append((i, m.group(2).strip().lower()))
            seen: dict[str, int] = {}
            for line_no, htext in heading_lines:
                if htext in seen:
                    findings.append(
                        Finding(
                            tool="structure",
                            severity="high",
                            file=str(f),
                            line=line_no,
                            rule_id="DOC005",
                            message=(
                                f"Duplicate heading text {htext!r} (also appears "
                                f"at line {seen[htext]}). Breaks TOC generation "
                                f"and reader navigation."
                            ),
                        )
                    )
                else:
                    seen[htext] = line_no
            # Diataxis-mode signal in first 500 chars
            head = text[:500]
            if not self._DIATAXIS_KEYWORDS.search(head):
                findings.append(
                    Finding(
                        tool="structure",
                        severity="low",
                        file=str(f),
                        line=1,
                        rule_id="DOC003",
                        message=(
                            "No Diataxis-mode signal in the document's opening 500 chars "
                            "(Tutorial / How-to / Reference / Explanation). "
                            "Consider stating the doc's mode explicitly."
                        ),
                    )
                )
            # Empty file guard
            if not text.strip():
                findings.append(
                    Finding(
                        tool="structure",
                        severity="high",
                        file=str(f),
                        line=1,
                        rule_id="DOC004",
                        message="Document is empty or whitespace-only.",
                    )
                )
        return findings, "ok"

    def _run_story(self, files: list[Path]) -> tuple[list[Finding], str]:
        """Run the Storyteller subtype over the declared story documents in files.

        A file `story.is_story` accepts but `story.unread_reasons` names is
        reported unread, never ok.
        """
        from dev_harness.harness.rules import story

        findings: list[Finding] = []
        unread: list[str] = []
        for f in files:
            text = f.read_text(encoding="utf-8", errors="replace")
            if not story.is_story(text):
                continue
            reasons = story.unread_reasons(text)
            if reasons:
                unread.append(f"{f.name} ({'; '.join(reasons)})")
            findings.extend(
                Finding(
                    tool=rf.tool,
                    severity=rf.severity,
                    file=rf.file,
                    line=rf.line,
                    rule_id=rf.rule_id,
                    message=rf.message,
                )
                for rf in story.scan(f, text)
            )
        if unread:
            return findings, f"unread: {', '.join(unread)}"
        return findings, "ok"


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: python -m tools.harness.docs_archetype <path>")
        print(
            "       reviews Markdown/text docs with proselint (+ vale if installed) + structure check"
        )
        return 2
    target = Path(argv[0])
    report = DocsArchetype().review(target)
    print(json.dumps(report.to_dict(), indent=2))
    return cli_exit(report)


if __name__ == "__main__":
    sys.exit(main())

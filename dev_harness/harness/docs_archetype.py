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
# S607 WAS SUPPRESSED HERE AND IT WAS NOT A FALSE POSITIVE.
#
# The directive claimed "resolved paths". Measured 2026-08-13 by
# stripping it: two S603 and one S607, at the vale runner.
# `_run_vale` called `shutil.which("vale")` into `vale_bin`, and the
# whole file referenced that name exactly twice -- the assignment
# and an `is None` test. The spawn discarded it and made the
# operating system search PATH a SECOND time. That is a
# time-of-check-to-time-of-use gap: `which` proves one binary
# exists and `subprocess.run` may then spawn a different one, on
# every gated Markdown write. A wrong `vale` scoring documentation
# would report findings the operator would read as this gate's
# verdict. The resolved path is now the thing that is spawned, so
# S607 reports zero here BY CONSTRUCTION rather than by suppression.
#
# S603 stays: measured across six argv shapes with ruff 0.16, an
# all-literal argv draws none and any argv carrying a variable draws
# one, and both runners must pass the target path.
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


# `Finding` and `ArchetypeReport` now live in tools/harness/report.py.
# Five archetypes each carried a copy. The copies drifted, and the
# drift shipped a green report for a run that checked nothing: an
# early return left `findings` empty, and "no high finding" answered
# True. `passed` now also requires that the target was scanned and
# that every required analyzer reported `ok`.


# ---------------------------------------------------------------------------
# proselint severity normalization
# ---------------------------------------------------------------------------

# proselint uses check names like `weasel_words.misc` and severity strings
# "error" | "warning" | "suggestion". Map to normalized levels.
# A curated set of proselint check families we consider material for a
# technical-documentation harness. Others still surface as low.
_PROSELINT_HIGH_FAMILIES = {
    "misc.illogic",  # logical errors
    "security",  # credentials-in-docs class
}

# v3.24.20 — typography.symbols DEMOTED out of the blocking set.
#
# It was listed above with the comment "actual bugs in text". Measured
# against the real corpus (40 markdown files under docs/ and the repo
# root, tools/harness/../scratchpad/prose_measure.py):
#
#     typography.symbols     747   96.6%   <- the entire blocking signal
#       .curly_quotes        735
#       .ellipsis             10
#       .copyright             2
#     misc.illogic             0
#     security                 0
#     everything else         26    3.4%
#
# So the docs gate blocked exclusively on curly quotes, and the two
# families that would catch something substantive have never fired once.
# Straight-vs-curly quotes is a house-style preference, not a defect, and
# in this repo the documents are audit reports whose bodies are quoted
# source code — "correcting" those quotes would corrupt the samples.
#
# Two concrete false positives this produced:
#   - `O(R)` (Big-O over reservations) matched typography.symbols.trademark
#     and was reported as "use the symbol (R)".
#   - `DB_PASSWORD = "hunter2"` inside a code span was linted as prose.
#
# The second is fixed properly by _strip_markdown_code below; this
# demotion handles the severity half.
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


# ---------------------------------------------------------------------------
# The archetype
# ---------------------------------------------------------------------------


class DocsArchetype:
    """Documentation-quality archetype. Invokes proselint (installed),
    and Vale if on PATH. Also does a light structural check for
    Diataxis-mode signal and H1 heading."""

    name = "documentation_quality"
    version = "1.1"  # v1.1: added falsification field + calibration hook
    tools = ("proselint", "vale", "structure")
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

        # Both returns above scanned NOTHING, and `scanned` stays
        # False for both. A directory holding no markdown is not a
        # directory of clean markdown, and neither is a path that
        # does not exist.
        report.scanned = True

        for tool_name, runner in [
            ("proselint", self._run_proselint),
            ("vale", self._run_vale),
            ("structure", self._run_structure),
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

        # v3.23.90 + v3.23.91 — universal rule modules. For markdown
        # targets, scaffolding S004 (placeholder text) + hallucination
        # H001 (dead path reference) + H002 (dead architecture ref)
        # all apply. S001-S003 and H003 are Python-only per their
        # suffix guards.
        #
        # 2026-08-13 — the rules now run over the files this archetype
        # ENUMERATED, not over `target.read_text()`. On a directory that
        # read raises, the caller substituted "" and both modules
        # reported `ok` having scanned nothing. MEASURED on a directory
        # holding one markdown file that cites a path which does not
        # exist: the FILE target reported hallucination H001, the
        # DIRECTORY target reported none and stayed green. For a single
        # file `files` is [target], so nothing changes there.
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

    # v3.23.44 — path patterns whose contents are provenance /
    # capture artefacts, not authored documentation. Excluded from
    # the docs archetype scan so their typographic style isn't
    # policed. Currently: raw subagent transcripts saved during
    # the archetype-peer-review harness build (2026-07-24 batch).
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
            # v3.24.20 — lint PROSE, not code. proselint has no markdown
            # model, so fenced blocks and inline spans were being linted as
            # English. Strip them to a line-count-preserving copy first so
            # reported line numbers still resolve against the real file.
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
            # `vale_bin`, not "vale". The resolved absolute path was
            # computed and thrown away, and the spawn searched PATH a
            # second time -- so what `which` proved and what ran were
            # two different lookups.
            proc = subprocess.run(
                # cwd pinned: vale resolves `.vale.ini` against the
                # current directory, so an unpinned caller got an
                # unconfigured vale and a RuntimeError instead of a
                # review.
                [vale_bin, "--output=JSON", str(f)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            # v3.24.34 (C43 follow-on) — vale reports RUNTIME errors as
            # JSON on STDERR and leaves stdout EMPTY. The bare
            # `if not proc.stdout.strip(): continue` below then treated
            # a total failure as "nothing to report" and the function
            # returned "ok".
            #
            # Measured with vale 3.17.1 installed and no .vale.ini:
            #   stdout : (empty)
            #   stderr : {"Code":"E100","Text":"E100 [.vale.ini not
            #             found] Runtime error ... no config file found"}
            #   rc     : 2
            # and the archetype reported vale:'ok', 0 findings,
            # passed=True. An installed-but-unconfigured vale was
            # strictly worse than an absent one, because absence was at
            # least reported honestly as 'missing'.
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

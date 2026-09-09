"""ESLint, Stylelint and html-validate, normalized into `Finding` rows.

`run_eslint`, `run_stylelint` and `run_html_validate` each return
`(findings, status)`, the shape the archetype runner tables consume.
Each raises FileNotFoundError when node or the package under
`NODE_MODULES` is absent, which a caller records as `missing`. `_run`
sets the working directory to `REPO_ROOT`, so `eslint.config.mjs`,
`.stylelintrc.json` and `.htmlvalidate.json` configure every call.
"""

# ruff: noqa: S603
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from dev_harness.harness.report import REPO_ROOT, Finding, refuse_silent_failure

__all__ = [
    "NODE_MODULES",
    "run_eslint",
    "run_html_validate",
    "run_stylelint",
]

#: `npm install` at the repo root installs every analyzer here.
NODE_MODULES: Path = REPO_ROOT / "node_modules"

_TIMEOUT_SECONDS = 180

_ESLINT_SEVERITY: dict[int, str] = {2: "high", 1: "medium"}
_STYLELINT_SEVERITY: dict[str, str] = {"error": "high", "warning": "medium"}
_HTML_VALIDATE_SEVERITY: dict[int, str] = {2: "high", 1: "medium"}

# A message carrying a null rule name still needs a rule_id in the report.
_NO_RULE = "no-rule"


def _node_executable() -> str:
    """Absolute path of the node interpreter, or FileNotFoundError."""
    node = shutil.which("node")
    if node is None:
        raise FileNotFoundError("node not on PATH")
    return node


def _package_script(package: str) -> str:
    """Absolute path of the CLI script `package` declares under `bin`."""
    manifest = NODE_MODULES / package / "package.json"
    try:
        declared = json.loads(manifest.read_text(encoding="utf-8")).get("bin")
    except (OSError, ValueError) as exc:
        raise FileNotFoundError(
            f"{package} is not installed under {NODE_MODULES}: {exc}"
        ) from exc
    relative = declared.get(package) if isinstance(declared, dict) else declared
    if not isinstance(relative, str):
        raise FileNotFoundError(f"{package} declares no bin script named {package}")
    script = NODE_MODULES / package / relative
    if not script.is_file():
        raise FileNotFoundError(f"{package} bin script is absent: {script}")
    return str(script)


def _run(package: str, args: list[str], target: Path) -> subprocess.CompletedProcess:
    """Run one analyzer over `target` with `REPO_ROOT` as working directory."""
    return subprocess.run(
        [_node_executable(), _package_script(package), *args, str(target)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )


def _parse_json(text: str, tool: str) -> list:
    """Parsed `text`, or RuntimeError when `tool` printed non-JSON."""
    if not text.strip():
        return []
    try:
        parsed = json.loads(text)
    except ValueError as exc:
        raise RuntimeError(f"{tool} produced non-JSON output: {exc}") from exc
    if not isinstance(parsed, list):
        raise RuntimeError(f"{tool} produced {type(parsed).__name__}, not a list")
    return parsed


def _stylelint_output(proc: subprocess.CompletedProcess) -> str:
    """Stdout of `proc`, or its stderr when stdout is empty.

    stylelint prints a clean report to stdout and a report carrying
    warnings to stderr, so `refuse_silent_failure` cannot read it.
    """
    text = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    if not text and proc.returncode != 0:
        raise RuntimeError(f"stylelint exited {proc.returncode} without output")
    return text


def run_eslint(target: Path) -> tuple[list[Finding], str]:
    """Grade one JavaScript file with eslint.

    A `fatal` message maps to critical and a rule violation to high.
    """
    proc = _run("eslint", ["--no-color", "--format", "json"], target)
    refuse_silent_failure(proc, "eslint")
    findings: list[Finding] = []
    for result in _parse_json(proc.stdout, "eslint"):
        path = result.get("filePath", str(target))
        for message in result.get("messages", []):
            severity = (
                "critical"
                if message.get("fatal")
                else _ESLINT_SEVERITY.get(message.get("severity"), "medium")
            )
            findings.append(
                Finding(
                    tool="eslint",
                    severity=severity,
                    file=path,
                    line=message.get("line", 0),
                    rule_id=message.get("ruleId") or _NO_RULE,
                    message=message.get("message", ""),
                )
            )
    return findings, "ok"


def run_stylelint(target: Path) -> tuple[list[Finding], str]:
    """Grade one CSS file with stylelint.

    `parseErrors` and `invalidOptionWarnings` map to critical, `warnings`
    to high or medium.
    """
    proc = _run("stylelint", ["--no-color", "--formatter", "json"], target)
    findings: list[Finding] = []
    for result in _parse_json(_stylelint_output(proc), "stylelint"):
        path = result.get("source") or str(target)
        for problem in result.get("parseErrors", []):
            findings.append(
                Finding(
                    tool="stylelint",
                    severity="critical",
                    file=path,
                    line=problem.get("line", 0),
                    rule_id=problem.get("rule") or "parse-error",
                    message=problem.get("text", ""),
                )
            )
        for problem in result.get("invalidOptionWarnings", []):
            findings.append(
                Finding(
                    tool="stylelint",
                    severity="critical",
                    file=path,
                    line=0,
                    rule_id="invalid-option",
                    message=problem.get("text", ""),
                )
            )
        for problem in result.get("warnings", []):
            findings.append(
                Finding(
                    tool="stylelint",
                    severity=_STYLELINT_SEVERITY.get(
                        problem.get("severity", ""), "medium"
                    ),
                    file=path,
                    line=problem.get("line", 0),
                    rule_id=problem.get("rule") or _NO_RULE,
                    message=problem.get("text", ""),
                )
            )
    return findings, "ok"


def run_html_validate(target: Path) -> tuple[list[Finding], str]:
    """Grade one HTML file with html-validate.

    Severity 2 maps to high and severity 1 to medium.
    """
    proc = _run("html-validate", ["--formatter", "json"], target)
    refuse_silent_failure(proc, "html-validate")
    findings: list[Finding] = []
    for result in _parse_json(proc.stdout, "html-validate"):
        path = result.get("filePath", str(target))
        for message in result.get("messages", []):
            findings.append(
                Finding(
                    tool="html-validate",
                    severity=_HTML_VALIDATE_SEVERITY.get(
                        message.get("severity"), "medium"
                    ),
                    file=path,
                    line=message.get("line", 0),
                    rule_id=message.get("ruleId") or _NO_RULE,
                    message=message.get("message", ""),
                )
            )
    return findings, "ok"

"""TA archetype — Chart and Quant checks for indicator code.

Operator, 2026-08-09: the harness needs four archetypes, "GUI, Coding,
TA (Chart + Quant), Docs".

WHY THIS EXISTS. On 2026-08-09 seven real defect classes from this
codebase were run past the existing harness. It caught three: a
hallucinated attribute, a hallucinated import, a dead parameter. It
missed four, and all four had already shipped:

  * `_wilder_smooth` documented "First value = sum/period" and returned
    the SUM. ADX ran at ~14x its definitional maximum for four minor
    versions. 99.8% of readings exceeded 100 on an index bounded at 100.
  * Slingshot `squeeze_conf` was clamped `min(1.0, x)` with no floor and
    reported confidences as low as -0.2722.
  * Bollinger `squeeze` compared a DIMENSIONLESS band width against an
    ABSOLUTE price width, so the flag reduced to `mid > 1.33`. Measured
    across 35 fleet symbols: every symbol at or below $0.42 squeezed on
    0.0% of windows, every symbol at or above $8.28 on 100.0%.
  * `adx_threshold = 500.0` sat on a quantity bounded at 100, because
    v3.20.22 recalibrated the threshold around the broken ADX instead of
    fixing it.

ruff, mypy, pyright, vulture, bandit and semgrep cannot see any of
those. Each one is valid syntax, correctly typed, every symbol
resolving. The defect is in what the numbers MEAN.

WHAT THIS CHECKS. Only patterns derived from defects that really
happened here. Every rule below has a named incident behind it.

  TA001  docstring promises an average over an undivided sum(...)
  TA002  one-sided clamp on a bounded quantity
  TA003  threshold constant outside its indicator's definitional range
  TA004  dimensionless ratio compared against an absolute magnitude
  TA010  chart: range normalisation with no zero guard
  TA011  chart: fixed-precision rounding of a price (medium)
  TA000  the file could not be read or parsed (info)

OVERTAKEN, kept whole: "TA011  chart: fixed-precision rounding of a
price (medium)". TA011 emits high and turns `passed` false.

This list was WRONG until 2026-08-13. It advertised a fifth quant
rule that no line of this file emits, and omitted both chart rules.
A rule list is a claim about what a clean report means, so a reader
of a green report believed five quant rules had cleared the file
when four had. Re-derived by listing every `rule_id=` literal in
the module.

TA001 keys on a literal `sum(...)`. An accumulation loop that
promises an average and never divides is outside its domain, and
`tests/test_ta_archetype.py` pins that boundary rather than a
wider claim.

FALSIFICATION. This archetype is wrong if it passes a file containing
any of the four incidents above. `tests/test_ta_archetype.py` holds one
reconstruction per rule, bad and good, in
`docs/audits/2026-08-13_ta_archetype/fixtures`; if a reconstruction
stops failing, or a corrected body starts failing, the rule has
stopped working.
"""

from __future__ import annotations

import ast
import json
import logging
import re
import subprocess
import sys
from pathlib import Path

from dev_harness.harness.report import (
    REPO_ROOT,
    ArchetypeReport,
    Finding,
    cli_exit,
    read_rule_sources,
    rule_source_files,
)

__all__ = ["ArchetypeReport", "Finding", "TAArchetype", "main"]

logger = logging.getLogger("acervator.ta_archetype")

# name -> (low, high), taken from the published indicator definitions and
# never from observed output.
BOUNDED: dict = {
    "adx": (0.0, 100.0),
    "di_plus": (0.0, 100.0),
    "di_minus": (0.0, 100.0),
    "plus_di": (0.0, 100.0),
    "minus_di": (0.0, 100.0),
    "rsi": (0.0, 100.0),
    "stoch_rsi": (0.0, 100.0),
    "mfi": (0.0, 100.0),
    "er": (0.0, 1.0),
    "kaufman_er": (0.0, 1.0),
    "cmf": (-1.0, 1.0),
    "bb_position": (0.0, 1.0),
}

# Anything whose name says it is a confidence or a probability is
# bounded [0, 1] by its own name.
CONFIDENCE_RE = re.compile(r"(conf|confidence|probability|pct_of|ratio)$")

AVERAGE_WORDS = re.compile(
    r"\b(average|averaging|mean|/\s*period|sum\s*/\s*period|divided by)\b", re.I
)


class _TAAnalyzer(ast.NodeVisitor):
    """AST pass for the Quant half."""

    def __init__(self, src: str, path: Path) -> None:
        self.src = src
        self.lines = src.split("\n")
        self.path = path
        self.findings: list[Finding] = []
        # Local names whose value came from a division. TA004 uses this
        # to tell a dimensionless quantity from an absolute one.
        self.divided: set = set()

    # -- TA001: docstring promises a mean, body never divides ---------
    def _check_average_promise(self, node) -> None:
        doc = ast.get_docstring(node) or ""
        if not AVERAGE_WORDS.search(doc):
            return
        # The signature is a `sum(...)` stored or returned with no division
        # applied to that same expression, not a division anywhere in the body.
        bare_sum = False
        for n in ast.walk(node):
            if not (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "sum"
            ):
                continue
            parent_divides = any(
                isinstance(pn, ast.BinOp)
                and isinstance(pn.op, (ast.Div, ast.FloorDiv))
                and any(c is n for c in ast.walk(pn.left))
                for pn in ast.walk(node)
            )
            if not parent_divides:
                bare_sum = True
                break
        if not bare_sum:
            return
        self.findings.append(
            Finding(
                tool="ta-quant",
                severity="high",
                file=str(self.path),
                line=node.lineno,
                rule_id="TA001",
                message=(
                    f"{node.name}: docstring promises an average or a "
                    f"sum/period, but the body contains no division. "
                    f"`_wilder_smooth` said 'First value = sum/period' and "
                    f"returned the sum; ADX ran at ~14x its bound for four "
                    f"minor versions."
                ),
            )
        )

    # Denominators that preserve units. Dividing by one of these leaves the
    # numerator's unit, so the quotient is not dimensionless.
    COUNT_DENOM = re.compile(
        r"^(period|periods|n|count|length|window|size|len|total|num|"
        r"samples?|bars?|step|step_ms|interval|interval_ms|tf|"
        r"granularity|ms|sec|secs|seconds)$",
        re.I,
    )

    # Names that make a `/` a PATH JOIN rather than arithmetic.
    PATHISH = re.compile(r"(path|dir|folder|home|root|file)", re.I)

    def _normalising_div(self, value: ast.AST) -> bool:
        """True when a division normalises units rather than averaging.

        v1.2 - `pathlib` overloads `/`, so
        `Path(...) / ".acervator" / "bot_state.json"` is an `ast.Div`
        and read as a normalising division. That put
        `BOT_STATE_PATH` in the dimensionless set and produced a units
        mismatch on `p.resolve() == BOT_STATE_PATH.resolve()` - two
        paths, no units at all. Two of seventeen findings in the first
        full scan were this.
        """
        for n in ast.walk(value):
            if not (
                isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Div, ast.FloorDiv))
            ):
                continue
            try:
                denom = ast.unparse(n.right)
                whole = ast.unparse(n)
            except Exception as exc:
                logger.debug("ta-quant: unparse failed: %s", exc)
                continue
            # A string operand or a path-ish name means this is a path
            # join, not arithmetic.
            if isinstance(n.right, ast.Constant) and isinstance(n.right.value, str):
                continue
            if isinstance(n.left, ast.Constant) and isinstance(n.left.value, str):
                continue
            if self.PATHISH.search(whole):
                continue
            base = re.sub(r"[^A-Za-z_]", " ", denom).split()
            # `len(x)` and bare counts average; anything else (mid,
            # price, sma, close) normalises.
            if base and all(self.COUNT_DENOM.match(b) for b in base):
                continue
            if not base:  # divided by a literal — not a unit change
                continue
            return True
        return False

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._normalising_div(node.value):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    self.divided.add(t.id)
                elif isinstance(t, ast.Attribute):
                    self.divided.add(t.attr)
        self._one_sided_clamp(node)
        self.generic_visit(node)

    def _one_sided_clamp(self, node: ast.Assign) -> None:
        target = ""
        if node.targets and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
        elif node.targets and isinstance(node.targets[0], ast.Attribute):
            target = node.targets[0].attr
        if not target:
            return
        bare = target.lstrip("_").lower()
        bounded = bare in BOUNDED or CONFIDENCE_RE.search(bare)
        if not bounded:
            return
        call = node.value
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
            return
        fn = call.func.id
        if fn not in ("min", "max"):
            return
        # A clamp is only complete when the OTHER side appears too.
        inner = ast.unparse(call)
        other = "max(" if fn == "min" else "min("
        if other in inner:
            return
        self.findings.append(
            Finding(
                tool="ta-quant",
                severity="high",
                file=str(self.path),
                line=node.lineno,
                rule_id="TA002",
                message=(
                    f"{target} is bounded but clamped with {fn}() only. "
                    f"Slingshot `squeeze_conf` used min(1.0, ...) with no "
                    f"floor and reported -0.2722. Clamp both ends."
                ),
            )
        )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_average_promise(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node) -> None:
        self._check_average_promise(node)
        self.generic_visit(node)

    # -- TA004: dimensionless compared to absolute -------------------
    def visit_Compare(self, node: ast.Compare) -> None:
        """Flag a comparison between a DIVIDED value and an undivided one.

        v1.1 — the first version compared NAMES, so it could not
        separate `band_width` from `avg_width`: both contain "width".
        That is the Bollinger incident exactly, and the rule missed it.

        What actually distinguishes them is provenance. `band_width`
        was produced by a division (`(upper - lower) / mid`) and is
        therefore dimensionless; `avg_width` was not and carries price
        units. Comparing them reduced a volatility flag to a test on
        price. So the check tracks which local names came from a
        division and flags a comparison that crosses that line.
        """
        try:
            left = ast.unparse(node.left)
            rights = [ast.unparse(c) for c in node.comparators]
        except Exception:
            self.generic_visit(node)
            return

        def _names(txt: str) -> set:
            return set(re.findall(r"[A-Za-z_]\w*", txt))

        def _is_literal(txt: str) -> bool:
            return bool(re.fullmatch(r"[-\d.eE+*/() ]+", txt.strip()))

        for r in rights:
            if _is_literal(r) or _is_literal(left):
                continue
            l_div = bool(_names(left) & self.divided)
            r_div = bool(_names(r) & self.divided)
            if l_div == r_div:
                continue
            self.findings.append(
                Finding(
                    tool="ta-quant",
                    severity="high",
                    file=str(self.path),
                    line=node.lineno,
                    rule_id="TA004",
                    message=(
                        f"units mismatch: '{left[:36]}' "
                        f"({'dimensionless' if l_div else 'absolute'}) compared "
                        f"against '{r[:36]}' "
                        f"({'dimensionless' if r_div else 'absolute'}). "
                        f"Bollinger squeeze compared a normalised band width "
                        f"against an ABSOLUTE price width; the flag reduced "
                        f"to `mid > 1.33` and 21 of 35 bots could never "
                        f"fire it."
                    ),
                )
            )
            break
        self.generic_visit(node)


def _strip_prose(src: str) -> str:
    """Blank comments and string literals, preserving offsets.

    Line numbers and match offsets must survive, so every removed
    character becomes a space and newlines are kept.
    """
    out = list(src)
    try:
        import io
        import tokenize

        lines = src.split(chr(10))
        starts = []
        acc = 0
        for ln in lines:
            starts.append(acc)
            acc += len(ln) + 1
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            # Python 3.12+ tokenises f-strings as FSTRING_MIDDLE, not STRING.
            _prose = {tokenize.COMMENT, tokenize.STRING}
            for _n in ("FSTRING_MIDDLE", "FSTRING_START", "FSTRING_END"):
                _t = getattr(tokenize, _n, None)
                if _t is not None:
                    _prose.add(_t)
            if tok.type not in _prose:
                continue
            (r1, c1), (r2, c2) = tok.start, tok.end
            beg = starts[r1 - 1] + c1
            end = starts[r2 - 1] + c2
            for i in range(beg, min(end, len(out))):
                if out[i] != chr(10):
                    out[i] = " "
    except Exception as exc:
        logger.debug("ta-quant: prose strip failed: %s", exc)
        return src
    return "".join(out)


def _run_quant(target: Path) -> list[Finding]:
    try:
        src = target.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src)
    except (OSError, SyntaxError) as exc:
        return [
            Finding(
                tool="ta-quant",
                severity="info",
                file=str(target),
                line=0,
                rule_id="TA000",
                message=f"unparsed: {exc}",
            )
        ]
    an = _TAAnalyzer(src, target)
    an.visit(tree)
    findings = list(an.findings)

    code = _strip_prose(src)

    # The indicator name matches the whole identifier or a snake_case part
    # of it, so `adx_threshold` matches `adx` and `WORKER` does not match `er`.
    for m in re.finditer(
        r"([A-Za-z_][A-Za-z0-9_]*)\s*" r"(?:=|>=|<=|>|<)\s*([0-9]+(?:\.[0-9]+)?)", code
    ):
        name, value = m.group(1), float(m.group(2))
        parts = {q.lower() for q in re.split(r"[^A-Za-z0-9]+", name) if q}
        parts.add(name.lower())
        key = next((k for k in BOUNDED if k in parts), None)
        if key is None:
            continue
        lo, hi = BOUNDED[key]
        if value > hi or value < lo:
            line = code[: m.start()].count("\n") + 1
            findings.append(
                Finding(
                    tool="ta-quant",
                    severity="high",
                    file=str(target),
                    line=line,
                    rule_id="TA003",
                    message=(
                        f"{m.group(1)} compared against {value}, outside the "
                        f"definitional range [{lo}, {hi}] for '{key}'. "
                        f"`adx_threshold = 500.0` was a recalibration around "
                        f"a broken ADX rather than a fix."
                    ),
                )
            )
    return findings


def _run_chart(target: Path) -> list[Finding]:
    """Chart half: rendering pitfalls that produce a wrong PICTURE.

    Derived from real defects: a divide-by-range with no guard blanks a
    chart on a flat series, and a fixed-precision round on an unbounded
    price collapses sub-cent assets to 0.0.
    """
    findings: list[Finding] = []
    try:
        src = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    if "paintEvent" not in src and "QPainter" not in src:
        return findings
    for i, line in enumerate(src.split("\n"), start=1):
        # range normalisation without a zero guard
        if re.search(r"/\s*\(?\s*(hi|high|mx|max_v)\s*-\s*(lo|low|mn|min_v)", line):
            window = src.split("\n")[max(0, i - 8) : i + 2]
            if not any(
                re.search(r"(if\s+hi\s*<=\s*lo|1e-9|or\s+1\b|max\(1)", w)
                for w in window
            ):
                findings.append(
                    Finding(
                        tool="ta-chart",
                        severity="high",
                        file=str(target),
                        line=i,
                        rule_id="TA010",
                        message=(
                            "range normalisation with no zero guard. A flat "
                            "series (high == low) is a real market state and "
                            "divides by zero here."
                        ),
                    )
                )
        # fixed-precision rounding of a price
        m = re.search(
            r"round\(\s*([\w\.\[\]'\"]*(?:price|px|close|"
            r"tenkan|kijun|senkou|level)[\w\.\[\]'\"]*)\s*,\s*(\d)\s*\)",
            line,
            re.I,
        )
        if m and int(m.group(2)) <= 4:
            findings.append(
                Finding(
                    tool="ta-chart",
                    severity="high",
                    file=str(target),
                    line=i,
                    rule_id="TA011",
                    message=(
                        f"round({m.group(1)}, {m.group(2)}) on a price. Assets "
                        f"below ~5e-5 collapse to 0.0; this fleet holds BONK "
                        f"at 0.0000045."
                    ),
                )
            )
    return findings


class TAArchetype:
    """Technical-analysis archetype: Quant (maths) + Chart (rendering)."""

    name = "ta_quality"
    version = "1.0"
    tools = ("ta-quant", "ta-chart", "ruff")
    calibration_name = "ta"

    def load_calibration(self) -> str:
        try:
            from dev_harness.harness.calibrations import load

            return load(self.calibration_name)
        except Exception:
            return ""

    def review(self, target: Path) -> ArchetypeReport:
        # The ruff subprocess below is pinned to the repo root, so a relative
        # target must be resolved here.
        target = Path(target).resolve()
        rep = ArchetypeReport(target=str(target))
        rep.falsification = (
            "This report is wrong if it passes a file containing any of: "
            "a docstring promising an average over a body that never "
            "divides (TA001); a one-sided clamp on a bounded quantity "
            "(TA002); a threshold outside an indicator's definitional "
            "range (TA003); a dimensionless value compared against an "
            "absolute one (TA004); a range normalisation with no zero "
            "guard (TA010); or a fixed-precision round on a price "
            "(TA011, medium, reported not blocking). "
            "OVERTAKEN: TA011 emits high and turns passed false. "
            "tests/test_ta_archetype.py reconstructs one real "
            "incident per rule, with the corrected body beside it."
        )
        if not target.exists():
            rep.errors.append(f"target not found: {target}")
            return rep

        # `scanned` stays False on the early return, so an empty report
        # cannot answer passed=True.
        rep.scanned = True

        sources, failures = read_rule_sources(rule_source_files(target, (".py",)))
        if failures or not sources:
            for detail in failures:
                rep.errors.append(f"source read failed: {detail}")
            if not sources:
                rep.errors.append(f"no python source to scan at: {target}")
            rep.tool_availability["ta-quant"] = "error"
            rep.tool_availability["ta-chart"] = "error"
            return rep
        for path, _src in sources:
            rep.findings.extend(_run_quant(path))
            rep.findings.extend(_run_chart(path))
        rep.tool_availability["ta-quant"] = "ok"
        rep.tool_availability["ta-chart"] = "ok"
        try:
            proc = subprocess.run(  # noqa: S603
                [
                    sys.executable,
                    "-m",
                    "ruff",
                    "check",
                    "--output-format=json",
                    "--no-cache",
                    "--select=NPY,PD,FURB,PLR2004",
                    str(target),
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=60,
            )
            # An absent `python -m ruff` does not raise: stdout is empty and
            # the return code is non-zero.
            if proc.returncode != 0 and not (proc.stdout or "").strip():
                detail = (proc.stderr or "").strip().replace("\n", " ")
                if "No module named ruff" in detail:
                    rep.tool_availability["ruff"] = "missing"
                    rep.errors.append("ruff: not installed")
                else:
                    rep.tool_availability["ruff"] = "error"
                    rep.errors.append(
                        f"ruff: exited {proc.returncode} without "
                        f"output: {detail[:240]}"
                    )
                return rep
            rep.tool_availability["ruff"] = "ok"
            for item in json.loads(proc.stdout or "[]"):
                rep.findings.append(
                    Finding(
                        tool="ruff",
                        severity="low",
                        file=str(target),
                        line=(item.get("location") or {}).get("row", 0),
                        rule_id=str(item.get("code") or "?"),
                        message=str(item.get("message") or ""),
                    )
                )
        except Exception as exc:
            rep.tool_availability["ruff"] = "error"
            rep.errors.append(f"ruff: {type(exc).__name__}: {exc}")
        return rep


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: python -m tools.harness.ta_archetype <path>")
        print("       reviews indicator maths (Quant) + chart rendering")
        return 2
    report = TAArchetype().review(Path(argv[0]))
    print(json.dumps(report.to_dict(), indent=2))
    return cli_exit(report)


if __name__ == "__main__":
    sys.exit(main())

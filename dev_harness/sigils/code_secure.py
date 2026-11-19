"""`SIGIL` is CODE.SECURE on the `core` card; `secure_check` judges one input line."""

import ast
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Collection, Iterator, Sequence
from dataclasses import dataclass
from functools import cache
from importlib import metadata
from pathlib import Path

from .coding_input import (
    CONTENT_TIER,
    DATA_TYPE_TIER,
    INPUT_FORM,
    OWNER,
    READERS,
    SEPARATOR,
    content_fault,
    data_type_fault,
    fault_file,
    locate,
)
from .coding_partition import SELECTION, selection
from .construct_rules import LEFT_BECAUSE, hold, house_rules
from .core import (
    APPLICATION_SOURCE,
    Flag,
    FlagRow,
    Reading,
    Sigil,
    Verdict,
    in_application_source,
    judge,
    main,
    tool_text,
)

CLEAN = "CLEAN"
WEAK = "WEAK"
REJECTED = "REJECTED"

BANDIT_BUILT = "1.9.4"
SEMGREP_BUILT = "1.171.0"
BANDIT_TIMEOUT_S = 120
SEMGREP_TIMEOUT_S = 180
SEMGREP_NO_RULE_TIMEOUT = "--timeout=0"
BANDIT_FINISHED = (0, 1)
SEMGREP_FINISHED = (0,)
BANDIT_STDIN = "<stdin>"
NO_CWE = "no CWE"
NO_TOOL = "no tool ran: the selection holds no rule of any tool on the card"
NO_OUTPUT = "nothing on stdout or stderr"
SEVERITIES = ("low", "medium", "high")
BANDIT_SEVERITY = {"LOW": "low", "MEDIUM": "medium", "HIGH": "high"}
SEMGREP_SEVERITY = {"INFO": "low", "WARNING": "medium", "ERROR": "high"}
SEMGREP_REGISTRY = "https://semgrep.dev/c/"
SEMGREP_PACKS = {
    "p/python": "de5bc79d074c3b4146338a0bf95830406f169bd91ac590a2f1ef111f162e23f5",
    "p/security-audit": "6d2f9a77b0372395072aa859ffd47f57b5851e1511da72a6c1b7ff9898ee1313",
}
PACK_FOLDER = Path(__file__).resolve().parent / "semgrep_rule_packs"
PACK_TEXT = PACK_FOLDER.relative_to(Path(__file__).resolve().parents[2]).as_posix()
FETCH = (
    "by hand, once per tree, never by a reading: for each pack, curl --fail "
    f"-H 'Accept: application/json' -H 'User-Agent: Semgrep/{SEMGREP_BUILT}' "
    f"--create-dirs --output-dir {PACK_TEXT} -o <file> {SEMGREP_REGISTRY}<pack>, "
    f"the address and headers semgrep {SEMGREP_BUILT} sends for a registry pack"
)

OWN_TOOL = "code_secure"
MASK_RULE = "SECURE001"
MASK_CWE = "CWE-532"
MASK_SEVERITY = SEMGREP_SEVERITY["WARNING"]
REQUIRED_WORDS = (
    "apikey",
    "secret",
    "password",
    "passphrase",
    "key",
    "token",
    "sign",
    "auth",
    "credential",
)
MIN_ENTRIES = 2
MIN_CREDENTIAL_WORDS = 2
MIN_PART_CHARS = 3
COLLECTION_CALLS = frozenset({"frozenset", "set", "tuple", "list"})
NAME_TEST_CALLS = frozenset({"any", "all"})
AFFIX_TESTS = frozenset({"startswith", "endswith"})
MUTATORS = frozenset(
    {"add", "update", "append", "extend", "insert", "discard", "remove", "pop", "clear"}
)
SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
BUILDERS = (ast.GeneratorExp, ast.ListComp, ast.SetComp)
REDACT_LINK = (
    "https://github.com/Acervator-LLC/ACERVATOR/commit/"
    "a703c49785626196ff5e0dd50712f240e5c973b1"
)
REDACT_QUOTE = (
    "_redact matched credential fields by key-name substring against {apikey, "
    'secret, password, passphrase, key, token}. "signature" contains none of them, '
    "so a param named signature, sign or CB-ACCESS-SIGN was never masked. A "
    "64-character HMAC arrived at the entry as its first 20 characters plus an "
    'ellipsis, via the >50-character truncation branch. Added "sign", "auth" and '
    '"credential" to the set.'
)
SCRUBBER_LINK = (
    "https://github.com/getsentry/sentry-python/blob/"
    "12c302b829d008e615e484bff7c24b56eec93f5e/sentry_sdk/scrubber.py"
)
SCRUBBER_QUOTE = (
    "A security denylist that is always scrubbed, defaults to DEFAULT_DENYLIST. "
    'return key.lower().replace("-", "_") '
    "if isinstance(k, str) and self._normalize_key(k) in self.denylist:"
)

_CWE_RE = re.compile(r"CWE-(\d+)")

Scope = ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda | ast.ClassDef
Bound = dict[str, list[ast.expr | None]]


def pack_name(pack: str) -> str:
    """Return the `PACK_FOLDER` file name of registry `pack`, such as p_python.yaml."""
    return pack.replace("/", "_") + ".yaml"


@dataclass(frozen=True)
class OwnRule:
    """One `OWN_RULES` rule: its `name`, `cwe`, `severity`, each quoted source and link in `sources`, and `reads`."""

    name: str
    cwe: str
    severity: str
    sources: tuple[tuple[str, str], ...]
    reads: Callable[[ast.Module], list[tuple[int, str]]]


def _entries(node: ast.expr | None) -> tuple[str, ...] | None:
    """Return the lowered entries of a tuple, list or set of `MIN_ENTRIES` or more str literals, or of a `COLLECTION_CALLS` call on one."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in COLLECTION_CALLS
        and len(node.args) == 1
        and not node.keywords
    ):
        node = node.args[0]
    if not isinstance(node, ast.Tuple | ast.List | ast.Set):
        return None
    words = [
        elt.value.lower()
        for elt in node.elts
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
    ]
    if len(words) < MIN_ENTRIES or len(words) != len(node.elts):
        return None
    return tuple(words)


def _is_credential(entry: str) -> bool:
    """Report whether `entry` holds a `REQUIRED_WORDS` word, or is a part of one `MIN_PART_CHARS` or more long."""
    return any(
        word in entry or (len(entry) >= MIN_PART_CHARS and entry in word)
        for word in REQUIRED_WORDS
    )


def _missing(entries: tuple[str, ...]) -> tuple[str, ...]:
    """Return each `REQUIRED_WORDS` word that no entry of `entries` is a substring of."""
    return tuple(
        word for word in REQUIRED_WORDS if not any(entry in word for entry in entries)
    )


def _scope_walk(scope: Scope) -> Iterator[ast.AST]:
    """Yield each node `scope` evaluates in its own namespace: no nested scope's body, no comprehension target."""
    stack: list[ast.AST] = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, SCOPE_NODES):
            continue
        if isinstance(node, ast.comprehension):
            stack.extend([node.iter, *node.ifs])
            continue
        stack.extend(ast.iter_child_nodes(node))


def _assigned(nodes: list[ast.AST]) -> tuple[dict[int, ast.expr], set[int]]:
    """Return the value each assignment target in `nodes` takes, and each target an annotation declares with no value."""
    values: dict[int, ast.expr] = {}
    declared: set[int] = set()
    for node in nodes:
        if isinstance(node, ast.Assign):
            values.update({id(target): node.value for target in node.targets})
        elif isinstance(node, ast.AnnAssign) and node.value is None:
            declared.add(id(node.target))
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            values[id(node.target)] = node.value
    return values, declared


def _binds(node: ast.AST) -> list[str]:
    """Return each name `node` binds as a parameter, an import, a def or class, an except clause or a match capture."""
    if isinstance(node, ast.arg):
        return [node.arg]
    if isinstance(node, ast.alias):
        return [(node.asname or node.name).partition(".")[0]]
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return [node.name]
    if isinstance(node, ast.ExceptHandler | ast.MatchAs | ast.MatchStar):
        return [node.name] if node.name else []
    if isinstance(node, ast.MatchMapping):
        return [node.rest] if node.rest else []
    return []


def _bound(scope: Scope) -> tuple[Bound, frozenset[str]]:
    """Return each name `scope` binds with the value of each binding, None unless a lone name is assigned, and its global names."""
    nodes = list(_scope_walk(scope))
    values, declared = _assigned(nodes)
    bound: Bound = {}
    for node in nodes:
        if (
            isinstance(node, ast.Name)
            and not isinstance(node.ctx, ast.Load)
            and id(node) not in declared
        ):
            bound.setdefault(node.id, []).append(values.get(id(node)))
        for name in _binds(node):
            bound.setdefault(name, []).append(None)
    globals_ = frozenset(
        name for node in nodes if isinstance(node, ast.Global) for name in node.names
    )
    return bound, globals_


def _mutated(tree: ast.Module) -> frozenset[str]:
    """Return each name `tree` calls a `MUTATORS` method on."""
    return frozenset(
        node.func.value.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in MUTATORS
        and isinstance(node.func.value, ast.Name)
    )


def _tests_name(elt: ast.expr, target: str) -> bool:
    """Report whether `elt` tests the name `target` against another value by in, not in, == or !=, or by startswith or endswith."""
    if isinstance(elt, ast.Compare) and len(elt.ops) == 1:
        sides = (elt.left, elt.comparators[0])
        held = [isinstance(side, ast.Name) and side.id == target for side in sides]
        return (
            isinstance(elt.ops[0], ast.In | ast.NotIn | ast.Eq | ast.NotEq)
            and held.count(True) == 1
            and not any(isinstance(side, ast.Constant) for side in sides)
        )
    return (
        isinstance(elt, ast.Call)
        and isinstance(elt.func, ast.Attribute)
        and elt.func.attr in AFFIX_TESTS
        and len(elt.args) == 1
        and isinstance(elt.args[0], ast.Name)
        and elt.args[0].id == target
    )


def _tested(node: ast.AST) -> Iterator[ast.expr]:
    """Yield the collection a name test at `node` reads: the right side of in or not in, or the iterable any or all reads."""
    if isinstance(node, ast.Compare):
        lefts = [node.left, *node.comparators[:-1]]
        for left, op, right in zip(lefts, node.ops, node.comparators, strict=True):
            if isinstance(op, ast.In | ast.NotIn) and not isinstance(left, ast.Constant):
                yield right
    elif (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in NAME_TEST_CALLS
        and len(node.args) == 1
        and isinstance(node.args[0], BUILDERS)
        and len(node.args[0].generators) == 1
    ):
        built = node.args[0]
        first = built.generators[0]
        if isinstance(first.target, ast.Name) and _tests_name(built.elt, first.target.id):
            yield first.iter


def _sites(tree: ast.Module) -> Iterator[tuple[ast.expr, int, tuple[Scope, ...]]]:
    """Yield each `_tested` collection in `tree`, the test's line, and the scopes its names resolve through, innermost first."""

    def visit(
        scope: Scope, outer: tuple[Scope, ...]
    ) -> Iterator[tuple[ast.expr, int, tuple[Scope, ...]]]:
        """Yield the sites of `scope`, then of each nested scope, which never sees a class's names."""
        chain = (scope, *outer)
        enclosing = outer if isinstance(scope, ast.ClassDef) else chain
        stack: list[ast.AST] = list(ast.iter_child_nodes(scope))
        while stack:
            node = stack.pop()
            if isinstance(node, SCOPE_NODES):
                yield from visit(node, enclosing)
                continue
            for collection in _tested(node):
                yield collection, getattr(node, "lineno", 0), chain
            stack.extend(ast.iter_child_nodes(node))

    yield from visit(tree, ())


def _mask_list_gaps(tree: ast.Module) -> list[tuple[int, str]]:
    """Return the line and missing words of each name test whose collection holds credential words and misses a `REQUIRED_WORDS` word."""
    scopes: dict[int, tuple[Bound, frozenset[str]]] = {}
    mutated = _mutated(tree)

    def resolve(name: str, chain: tuple[Scope, ...]) -> tuple[str, ...] | None:
        """Return `_entries` of the one binding of `name` in its nearest `chain` scope, else None."""
        if name in mutated:
            return None
        for scope in chain:
            if id(scope) not in scopes:
                scopes[id(scope)] = _bound(scope)
            bound, globals_ = scopes[id(scope)]
            if name in globals_ or name not in bound:
                continue
            values = bound[name]
            return _entries(values[0]) if len(values) == 1 else None
        return None

    gaps: dict[int, str] = {}
    for collection, line, chain in _sites(tree):
        entries = (
            resolve(collection.id, chain)
            if isinstance(collection, ast.Name)
            else _entries(collection)
        )
        if entries is None:
            continue
        missing = _missing(entries)
        credentials = [entry for entry in entries if _is_credential(entry)]
        if missing and len(credentials) >= MIN_CREDENTIAL_WORDS:
            gaps[line] = "missing " + ", ".join(missing)
    return sorted(gaps.items())


OWN_RULES: dict[str, OwnRule] = {
    MASK_RULE: OwnRule(
        "credential-mask-missing-word",
        MASK_CWE,
        MASK_SEVERITY,
        ((REDACT_QUOTE, REDACT_LINK), (SCRUBBER_QUOTE, SCRUBBER_LINK)),
        _mask_list_gaps,
    ),
}

FUNCTION = (
    "reads each call, query, secret, parse and path for a weakness an attacker "
    "can use, with the CWE id each tool attaches to it"
)
DISCIPLINES = ("python",)
CHARACTERISTICS = ("security",)
BANDIT = hold("bandit", house_rules("bandit"), DISCIPLINES, CHARACTERISTICS)
SEMGREP = hold("semgrep", house_rules("semgrep"), DISCIPLINES, CHARACTERISTICS)
OWN = hold(OWN_TOOL, tuple(OWN_RULES), DISCIPLINES, CHARACTERISTICS)
CAN_RUN = tuple(
    f"{held.tool} {rule}" for held in (BANDIT, SEMGREP, OWN) for rule in held.rules
)

SETTINGS: dict[str, str] = {
    "separator": SEPARATOR,
    "bandit_version": BANDIT_BUILT,
    "semgrep_version": SEMGREP_BUILT,
    "semgrep_pack_folder": PACK_TEXT,
    "semgrep_packs": "; ".join(
        f"{pack} as {pack_name(pack)}, sha256 {digest}"
        for pack, digest in SEMGREP_PACKS.items()
    ),
    "function": FUNCTION,
    "disciplines": " ".join(DISCIPLINES),
    "characteristics": " ".join(CHARACTERISTICS),
    "scope": "each bandit test and semgrep rule a discipline houses or unplaced.json "
    "lists: the tests python -m bandit --help lists, and the rules p/python and "
    f"p/security-audit hold; and {MASK_RULE}, the one rule this module runs itself",
    "bandit_rules": " ".join(BANDIT.rules),
    "semgrep_rules": " ".join(SEMGREP.rules),
    "own_tool": OWN.tool,
    "own_rules": " ".join(OWN.rules),
    "own_reads": f"Python's ast module: {MASK_RULE} reads each tuple, list, set or "
    "frozenset of str literals that a name test reads, and names each of "
    "required_words that no entry of it is a substring of",
    "required_words": " ".join(REQUIRED_WORDS),
    "selection": SELECTION,
    "can_run": str(len(CAN_RUN)),
    "severity_floor": "medium",
    "fault_file": "the file the input line names: WEAK reads HOLD when it sits "
    "in application_source and a finding reaches severity_floor",
}


class ToolFault(Exception):
    """bandit or semgrep did not finish, printed an unreadable report, or a
    `SEMGREP_PACKS` file failed its check."""


@dataclass(frozen=True)
class Finding:
    """One finding: the `tool`, its `rule` id, `cwe` id, `severity`, `line`, and an own rule's `detail`."""

    tool: str
    rule: str
    cwe: str
    severity: str
    line: int
    detail: str = ""


@cache
def bandit_version() -> str:
    """Return the installed bandit version `python -P -m bandit` runs."""
    return metadata.version("bandit")


def _said(proc: subprocess.CompletedProcess[bytes]) -> str:
    """Return what `proc` printed on stderr, else on stdout, else `NO_OUTPUT`."""
    return tool_text(proc.stderr) or tool_text(proc.stdout) or NO_OUTPUT


def _semgrep_cwe(cwe: object) -> str:
    """Return each CWE id in a semgrep `cwe` entry, joined, or `NO_CWE`."""
    texts = [cwe] if isinstance(cwe, str) else cwe if isinstance(cwe, list) else []
    ids = [f"CWE-{number}" for text in texts for number in _CWE_RE.findall(str(text))]
    return ", ".join(dict.fromkeys(ids)) or NO_CWE


def _bandit_findings(source: bytes, tests: tuple[str, ...]) -> list[Finding]:
    """Return each bandit `Finding` for `source`, read on stdin by the `tests` named."""
    argv = [sys.executable, "-P", "-m", "bandit", "-f", "json", "-q"]
    try:
        proc = subprocess.run(
            [*argv, "-t", ",".join(tests), "-"],
            input=source,
            capture_output=True,
            timeout=BANDIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        message = f"bandit: {exc}"
        raise ToolFault(message) from exc
    if proc.returncode not in BANDIT_FINISHED:
        message = f"bandit exited {proc.returncode}: {_said(proc)}"
        raise ToolFault(message)
    try:
        report = json.loads(proc.stdout)
        if report["errors"] or BANDIT_STDIN not in report["metrics"]:
            message = f"bandit did not read the file: {report['errors']}"
            raise ToolFault(message)
        return [
            Finding(
                "bandit",
                row["test_id"],
                f"CWE-{row['issue_cwe']['id']}" if row["issue_cwe"]["id"] else NO_CWE,
                BANDIT_SEVERITY[row["issue_severity"]],
                row["line_number"],
            )
            for row in report["results"]
        ]
    except (ValueError, KeyError, TypeError) as exc:
        message = f"bandit printed an unreadable report: {exc!r}"
        raise ToolFault(message) from exc


def _held_packs() -> list[Path]:
    """Return each `SEMGREP_PACKS` file in `PACK_FOLDER`, or raise `ToolFault`
    naming an unread path or both sha256 values."""
    held = []
    for pack, card_sha256 in SEMGREP_PACKS.items():
        path = PACK_FOLDER / pack_name(pack)
        where = f"{PACK_TEXT}/{pack_name(pack)}"
        try:
            found = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            message = f"held semgrep pack {where} cannot be read: {exc.strerror or exc}"
            raise ToolFault(message) from exc
        if found != card_sha256:
            message = (
                f"held semgrep pack {where} has sha256 {found}; "
                f"the card holds {card_sha256}"
            )
            raise ToolFault(message)
        held.append(path)
    return held


def _semgrep_findings(
    name: str, source: bytes, excluded: tuple[str, ...]
) -> tuple[str, list[Finding]]:
    """Return the semgrep version and each `Finding` for `source` copied as `name`, no `excluded` rule run."""
    packs = _held_packs()
    with tempfile.TemporaryDirectory() as folder:
        Path(folder, name).write_bytes(source)
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-P",
                    "-c",
                    "from semgrep.console_scripts.entrypoint import main; main()",
                    "scan",
                    *(f"--config={pack}" for pack in packs),
                    "--json",
                    "--metrics=off",
                    "--disable-version-check",
                    "--no-rewrite-rule-ids",
                    "--no-git-ignore",
                    SEMGREP_NO_RULE_TIMEOUT,
                    *(f"--exclude-rule={rule}" for rule in excluded),
                    ".",
                ],
                cwd=folder,
                env={**os.environ, "PYTHONUTF8": "1"},
                capture_output=True,
                timeout=SEMGREP_TIMEOUT_S,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            message = f"semgrep: {exc}"
            raise ToolFault(message) from exc
    if proc.returncode not in SEMGREP_FINISHED:
        message = f"semgrep exited {proc.returncode}: {_said(proc)}"
        raise ToolFault(message)
    try:
        report = json.loads(proc.stdout)
        if report["errors"]:
            message = f"semgrep reported errors: {report['errors']}"
            raise ToolFault(message)
        if report["paths"]["scanned"] != [name]:
            message = f"semgrep scanned {report['paths']['scanned']}, not {name}"
            raise ToolFault(message)
        return report["version"], [
            Finding(
                "semgrep",
                row["check_id"],
                _semgrep_cwe(row["extra"].get("metadata", {}).get("cwe")),
                SEMGREP_SEVERITY[row["extra"]["severity"]],
                row["start"]["line"],
            )
            for row in report["results"]
        ]
    except (ValueError, KeyError, TypeError) as exc:
        message = f"semgrep printed an unreadable report: {exc!r}"
        raise ToolFault(message) from exc


def _own_findings(source: bytes, codes: tuple[str, ...]) -> list[Finding]:
    """Return each `Finding` that an `OWN_RULES` rule of `codes` reads in `source` through Python's ast module."""
    tree = ast.parse(source)
    return [
        Finding(OWN.tool, code, OWN_RULES[code].cwe, OWN_RULES[code].severity, line, detail)
        for code in codes
        for line, detail in OWN_RULES[code].reads(tree)
    ]


def findings(text: str, root: Path, to_run: Collection[str]) -> tuple[str, list[Finding]]:
    """Return the tools run and each `Finding` of the `to_run` rules inside the input `text` names."""
    located = locate(text, root)
    if isinstance(located, str):
        message = f"{text}: {located}, after tier 2 accepted it"
        raise ToolFault(message)
    file, source, (first, last) = located
    is_narrowed = bool(text.partition(SETTINGS["separator"])[1])
    tests = tuple(rule for rule in BANDIT.rules if f"{BANDIT.tool} {rule}" in to_run)
    rules = [rule for rule in SEMGREP.rules if f"{SEMGREP.tool} {rule}" in to_run]
    own = tuple(rule for rule in OWN.rules if f"{OWN.tool} {rule}" in to_run)
    ran: list[str] = []
    found: list[Finding] = []
    if tests:
        ran.append(f"bandit {bandit_version()}")
        found += _bandit_findings(source, tests)
    if rules:
        excluded = tuple(rule for rule in SEMGREP.rules if rule not in rules)
        semgrep_ran, semgrep_found = _semgrep_findings(file.name, source, excluded)
        ran.append(f"semgrep {semgrep_ran}")
        found += semgrep_found
    if own:
        ran.append(f"{OWN.tool} on Python {platform.python_version()}")
        found += _own_findings(source, own)
    kept = [
        finding
        for finding in found
        if f"{finding.tool} {finding.rule}" in to_run
        and (not is_narrowed or first <= finding.line <= last)
    ]
    return ", ".join(ran) or NO_TOOL, kept


def _row(item: Finding) -> str:
    """Return the reading row of `item`: tool, rule, CWE, severity, any `detail`, and line."""
    detail = f" {item.detail}" if item.detail else ""
    return f"{item.tool} {item.rule} {item.cwe} {item.severity}{detail} line {item.line}"


def _source(code: str) -> str:
    """Return the line quoting each of `OWN_RULES` rule `code`'s sources with its link."""
    quoted = "; ".join(f'"{quote}" {link}' for quote, link in OWN_RULES[code].sources)
    return f"\n{code} source: {quoted}"


def _functions_verdict(text: str, root: Path) -> Reading:
    """Return `CLEAN`, or `WEAK` holding when a finding of the `selection` rules reaches `severity_floor`."""
    versions, found = findings(text, root, selection(text, root, CAN_RUN))
    if not found:
        return Reading(
            CLEAN,
            f"{versions}: no tool reports a finding under a rule on the card",
            holds=False,
        )
    floor = SEVERITIES.index(SETTINGS["severity_floor"])
    holds = any(SEVERITIES.index(finding.severity) >= floor for finding in found)
    rows = "; ".join(_row(item) for item in found)
    own = dict.fromkeys(item.rule for item in found if item.tool == OWN.tool)
    sources = "".join(_source(code) for code in own)
    return Reading(WEAK, f"{versions}: {rows}{sources}", holds)


SIGIL = Sigil(
    name="CODE.SECURE",
    edition=1,
    owner=OWNER,
    disciplines=DISCIPLINES,
    input_form=INPUT_FORM,
    settings=SETTINGS,
    tiers=(
        DATA_TYPE_TIER,
        CONTENT_TIER,
        {
            "runs": [
                "the selection: the rules of the card that coding_partition.select "
                "gives for the input's facts",
                (
                    "bandit, as python -P -m bandit -f json -q -t <the selected tests> -, "
                    "with the file's bytes on stdin, when the selection holds a bandit test"
                ),
                (
                    "semgrep, through semgrep.console_scripts.entrypoint, as semgrep "
                    "scan with a --config for each held pack in semgrep_pack_folder "
                    "once its sha256 matches semgrep_packs, --json --metrics=off "
                    "--disable-version-check --no-rewrite-rule-ids --no-git-ignore "
                    "--timeout=0, so no rule stops on a per-rule time limit, and "
                    "PYTHONUTF8=1, so each pack is read as UTF-8, with --exclude-rule "
                    "for each semgrep rule of the card the selection leaves out, in "
                    "an empty temporary folder holding a copy of the file under its "
                    "own name, when the selection holds a semgrep rule"
                ),
                (
                    f"{MASK_RULE}, when the selection holds it: Python's ast module "
                    "parses the file, and a name test is the right side of in or not "
                    "in under a left side that is no literal, or the iterable of a "
                    "builder that any or all reads, whose element tests the builder's "
                    "name by in, not in, ==, != , startswith or endswith; its "
                    "collection is a tuple, list, set, or frozenset, set, tuple or "
                    "list call, of two or more str literals, written in the test or "
                    "bound once to a name in the nearest scope that binds it, with "
                    "no add, update, append, extend, insert, discard, remove, pop or "
                    "clear call on that name; it reports the test's line when the "
                    "collection holds two or more credential words, each holding one "
                    "of required_words or being a part of one at least three "
                    "characters long, and a word of required_words has no entry that "
                    "is a substring of it"
                ),
                "only the findings under the selected rules",
                "for a symbol, only the findings inside its lines",
            ],
            "clean": "no tool reports a finding under a rule on the card",
            "weak": [
                "tool",
                "rule id",
                "CWE id",
                "severity",
                f"for {MASK_RULE}, the required words no entry covers",
                "line",
                "for an own rule, each source quoted with its link",
            ],
            "cwe": "the CWE id each tool reports for its own finding, else no CWE; "
            f"{MASK_CWE} for {MASK_RULE}",
            "severity": {
                "bandit": BANDIT_SEVERITY,
                "semgrep": SEMGREP_SEVERITY,
                OWN.tool: {MASK_RULE: MASK_SEVERITY},
            },
            "left": {
                BANDIT.tool: BANDIT.left,
                SEMGREP.tool: SEMGREP.left,
                OWN.tool: OWN.left,
            },
            "left_because": LEFT_BECAUSE,
            "not_held": "a finding under a rule outside the scope moves no verdict",
            "fetches": FETCH,
            "refuses": "a held pack that cannot be read, naming its path, or whose "
            "sha256 differs from semgrep_packs, naming both sha256 values; a tool "
            "that exits otherwise, naming what it printed, reports an error, "
            "or did not read the file",
        },
    ),
    outputs={
        CLEAN: FlagRow(Flag.PASS),
        WEAK: FlagRow(Flag.FIX, holds_in_source=True),
    },
    refusal=REJECTED,
    follows={},
    readers=READERS,
    data_type=data_type_fault,
    content=content_fault,
    functions=_functions_verdict,
    fault_file=fault_file,
)


def secure_check(
    text: str, root: Path, source: Sequence[str] = APPLICATION_SOURCE
) -> Verdict:
    """Return the `judge` verdict of `SIGIL` for one input line under `root`."""
    named = fault_file(text, root)
    in_source = named is not None and in_application_source(named, root, source)
    return judge(SIGIL, text, root, in_source=in_source)


def run(argv: list[str] | None = None) -> int:
    """Return `main` for `SIGIL`, or 1 with the `ToolFault` on stderr."""
    try:
        return main(SIGIL, argv)
    except ToolFault as exc:
        print(f"bandit or semgrep did not run: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())

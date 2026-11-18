"""`SIGIL` is CODE.LOOP on the `core` card; `loop_check` judges one input line."""

import ast
import sys
from collections.abc import Callable, Collection, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from .coding_input import (
    CONTENT_TIER,
    DATA_TYPE_TIER,
    INPUT_FORM,
    OWNER,
    READERS,
    SEPARATOR,
    data_type_fault,
    fault_file,
    locate,
)
from .coding_partition import SELECTION, selection
from .construct_rules import TOOL, hold, take
from .core import (
    APPLICATION_SOURCE,
    FLAGS,
    Flag,
    FlagRow,
    Reading,
    Sigil,
    Verdict,
    in_application_source,
    judge,
    main,
)
from .fix_class import BY_FIX_CLASS, FOLLOW_ON
from .ruff_rules import (
    RUFF_BUILT,
    RulePage,
    ToolFault,
    check,
    rule_page,
    ruff_version,
)

CLEAN = "CLEAN"
FINDINGS = "FINDINGS"
REJECTED = "REJECTED"

FUNCTION = (
    "reads each loop and comprehension for the faults that give a wrong result, "
    "waste work, or write by hand what Python's own forms already state"
)
DISCIPLINES = ("python",)
CHARACTERISTICS = ("conventions", "performance-efficiency", "reliability")
TAKEN = take("loop", DISCIPLINES, CHARACTERISTICS)
RULES = TAKEN.rules
PREVIEW = TAKEN.preview
HOLDING = TAKEN.holding
LOOP_NODES = (
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)
NO_LOOP = (
    "no for, async for, while, list, set or dictionary builder, "
    "or generator expression"
)

OWN_TOOL = "code_loop"
LIST = "list"
STR = "str"
OTHER = "other"
DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
NESTED = (*DEFS, ast.Lambda)
METHODS = (ast.FunctionDef, ast.AsyncFunctionDef)
QUEUE_LINK = (
    "https://docs.python.org/3.14/tutorial/datastructures.html#using-lists-as-queues"
)
QUEUE_QUOTE = (
    "While appends and pops from the end of list are fast, doing inserts or pops "
    "from the beginning of a list is slow (because all of the other elements have "
    "to be shifted by one). See Time complexity of operations on built-in types for "
    "more information. To implement a queue, use collections.deque which was "
    "designed to have fast appends and pops from both ends."
)
CONCAT_LINK = (
    "https://docs.python.org/3.14/builtins/stdtypes.html"
    "#typesseq-repeated-concatenation"
)
CONCAT_QUOTE = (
    "Concatenating immutable sequences always results in a new object. This means "
    "that building up a sequence by repeated concatenation will have a quadratic "
    "runtime cost in the total sequence length. To get a linear runtime cost, you "
    "must switch to one of the alternatives below: if concatenating str objects, you "
    "can build a list and use str.join() at the end or else write to an io.StringIO "
    "instance and retrieve its value when complete"
)

Scope = ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda
LoopNode = (
    ast.For
    | ast.AsyncFor
    | ast.While
    | ast.ListComp
    | ast.SetComp
    | ast.DictComp
    | ast.GeneratorExp
)
Chain = tuple[dict[str, set[str]], ...]
Node = ast.expr | ast.stmt


@dataclass(frozen=True)
class Found:
    """One `findings` item: the `tool` that read it, the rule `code` and its `line`."""

    tool: str
    code: str
    line: int


@dataclass(frozen=True)
class OwnRule:
    """One `OWN_RULES` rule: its `page`, each quoted source and link in `sources`, and `matches`."""

    page: RulePage
    sources: tuple[tuple[str, str], ...]
    matches: Callable[[Node, Chain, frozenset[str]], bool]


def _value_kind(value: ast.expr | None) -> str:
    """Return `LIST` or `STR` when `value` builds a list or a str, else `OTHER`."""
    if isinstance(value, ast.List | ast.ListComp):
        return LIST
    if isinstance(value, ast.JoinedStr) or (
        isinstance(value, ast.Constant) and isinstance(value.value, str)
    ):
        return STR
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id in {LIST, STR}
    ):
        return value.func.id
    return OTHER


def _annotation_kind(annotation: ast.expr | None) -> str:
    """Return `LIST` or `STR` when `annotation` names list, a list subscript, or str, else `OTHER`."""
    named = annotation.value if isinstance(annotation, ast.Subscript) else annotation
    if isinstance(named, ast.Name) and named.id in {LIST, STR}:
        return named.id
    return OTHER


def _key(expr: ast.expr | None) -> str | None:
    """Return the name `expr` reads, or `owner.attr` for an attribute of a name, else None."""
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
        return f"{expr.value.id}.{expr.attr}"
    return None


def _addends(value: ast.expr | None) -> list[ast.expr]:
    """Return the operands of `value` when it is a chain of `+`, else none."""
    if not (isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add)):
        return []
    return [
        *(_addends(value.left) or [value.left]),
        *(_addends(value.right) or [value.right]),
    ]


def _derives(value: ast.expr | None, key: str) -> bool:
    """Report whether `value` slices `key` or adds `key` to something, so it keeps the old value."""
    if isinstance(value, ast.Subscript):
        return _key(value.value) == key and isinstance(value.slice, ast.Slice)
    return any(_key(part) == key for part in _addends(value))


def _inside(scope: Scope) -> Iterator[ast.AST]:
    """Yield each node of `scope`'s body, parent first, never entering a `NESTED` body."""
    body = scope.body
    stack: list[ast.AST] = [body] if isinstance(body, ast.expr) else list(body)
    stack.reverse()
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, NESTED):
            stack.extend(reversed(list(ast.iter_child_nodes(node))))


def _other_names(node: ast.AST) -> list[str]:
    """Return each name `node` binds by a def, class, import, except, global, nonlocal or match."""
    if isinstance(node, DEFS):
        return [node.name]
    if isinstance(node, ast.Import | ast.ImportFrom):
        return [(alias.asname or alias.name).partition(".")[0] for alias in node.names]
    if isinstance(node, ast.Global | ast.Nonlocal):
        return list(node.names)
    if isinstance(node, ast.ExceptHandler | ast.MatchAs | ast.MatchStar):
        return [node.name] if node.name else []
    if isinstance(node, ast.MatchMapping):
        return [node.rest] if node.rest else []
    return []


def _kinds(scope: Scope) -> dict[str, set[str]]:
    """Return each name `scope` binds, with the `LIST`, `STR` or `OTHER` kind of every binding."""
    kinds: dict[str, set[str]] = {}
    if not isinstance(scope, ast.Module | ast.ClassDef):
        params = scope.args
        for arg in (*params.posonlyargs, *params.args, *params.kwonlyargs):
            kinds.setdefault(arg.arg, set()).add(_annotation_kind(arg.annotation))
        for rest in (params.vararg, params.kwarg):
            if rest is not None:
                kinds.setdefault(rest.arg, set()).add(OTHER)
    typed: set[int] = set()
    for node in _inside(scope):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    typed.add(id(target))
                    if not _derives(node.value, target.id):
                        kinds.setdefault(target.id, set()).add(_value_kind(node.value))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            kinds.setdefault(node.target.id, set()).add(
                _annotation_kind(node.annotation)
            )
            typed.add(id(node.target))
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            typed.add(id(node.target))
        elif isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            if id(node) not in typed:
                kinds.setdefault(node.id, set()).add(OTHER)
        for name in _other_names(node):
            kinds.setdefault(name, set()).add(OTHER)
    return kinds


def _first_param(method: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """Return the name of `method`'s first positional parameter, or None."""
    params = [*method.args.posonlyargs, *method.args.args]
    return params[0].arg if params else None


def _owned(node: ast.AST, owner: str) -> str | None:
    """Return the attribute `node` names on the name `owner`, else None."""
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == owner
    ):
        return node.attr
    return None


def _attribute_kinds(cls: ast.ClassDef) -> dict[str, set[str]]:
    """Return each attribute `cls`'s methods bind on their first parameter, with the kind of every binding."""
    kinds: dict[str, set[str]] = {}
    for method in cls.body:
        owner = _first_param(method) if isinstance(method, METHODS) else None
        if owner is None:
            continue
        typed: set[int] = set()
        for node in ast.walk(method):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    attr = _owned(target, owner)
                    if attr is not None:
                        typed.add(id(target))
                        if not _derives(node.value, f"{owner}.{attr}"):
                            kinds.setdefault(attr, set()).add(_value_kind(node.value))
            elif isinstance(node, ast.AnnAssign | ast.AugAssign):
                attr = _owned(node.target, owner)
                if attr is not None:
                    typed.add(id(node.target))
                    if isinstance(node, ast.AnnAssign):
                        kinds.setdefault(attr, set()).add(
                            _annotation_kind(node.annotation)
                        )
            elif isinstance(node, ast.Attribute) and not isinstance(node.ctx, ast.Load):
                attr = _owned(node, owner)
                if attr is not None and id(node) not in typed:
                    kinds.setdefault(attr, set()).add(OTHER)
    return kinds


def _loops(tree: ast.Module) -> Iterator[tuple[LoopNode, Chain]]:
    """Yield each loop in `tree` with the `_kinds` of each scope its names resolve through, innermost first."""

    def visit(
        scope: Scope, outer: Chain, members: dict[str, set[str]]
    ) -> Iterator[tuple[LoopNode, Chain]]:
        """Yield each loop of `scope`, then of each `NESTED` scope, with `members` keyed by `_first_param`."""
        kinds = _kinds(scope)
        owner = _first_param(scope) if isinstance(scope, METHODS) else None
        if owner is not None:
            kinds.update({f"{owner}.{attr}": found for attr, found in members.items()})
        chain = (kinds, *outer)
        enclosing = outer if isinstance(scope, ast.ClassDef) else chain
        inner = _attribute_kinds(scope) if isinstance(scope, ast.ClassDef) else {}
        for node in _inside(scope):
            if isinstance(node, LOOP_NODES):
                yield node, chain
            elif isinstance(node, NESTED):
                yield from visit(node, enclosing, inner)

    yield from visit(tree, (), {})


def _repeated(loop: LoopNode) -> list[ast.AST]:
    """Return the parts of `loop` that run on each pass: body, while test, or builder element and conditions."""
    if isinstance(loop, ast.For | ast.AsyncFor):
        return list(loop.body)
    if isinstance(loop, ast.While):
        return [loop.test, *loop.body]
    parts: list[ast.AST] = (
        [loop.key, loop.value] if isinstance(loop, ast.DictComp) else [loop.elt]
    )
    for index, generator in enumerate(loop.generators):
        parts.extend(generator.ifs)
        if index:
            parts.append(generator.iter)
    return parts


def _walk(parts: list[ast.AST]) -> Iterator[ast.AST]:
    """Yield each node under `parts`, never entering a `NESTED` body."""
    stack = list(parts)
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, NESTED):
            stack.extend(ast.iter_child_nodes(node))


def _rebound(loop: LoopNode) -> frozenset[str]:
    """Return each `_key` a `_repeated` part of `loop` binds afresh: not by `+=`, nor from its own value."""
    nodes = list(_walk(_repeated(loop)))
    carrying = {id(node.target) for node in nodes if isinstance(node, ast.AugAssign)}
    carrying |= {
        id(target)
        for node in nodes
        if isinstance(node, ast.Assign)
        for target in node.targets
        if _derives(node.value, _key(target) or "")
    }
    keys = (
        _key(node)
        for node in nodes
        if isinstance(node, ast.Name | ast.Attribute)
        and not isinstance(node.ctx, ast.Load)
        and id(node) not in carrying
    )
    return frozenset(key for key in keys if key is not None)


def _kind(expr: ast.expr, chain: Chain) -> str:
    """Return the one kind every binding gives the `_key` of `expr` in its nearest `chain` scope, else `OTHER`."""
    key = _key(expr)
    for kinds in chain:
        if key is not None and key in kinds:
            found = kinds[key]
            return next(iter(found)) if len(found) == 1 else OTHER
    return OTHER


def _carried(expr: ast.expr, chain: Chain, rebound: frozenset[str]) -> str:
    """Return `_kind` of `expr` when its `_key` is not in `rebound`, else `OTHER`."""
    if _key(expr) in rebound:
        return OTHER
    return _kind(expr, chain)


def _int_value(expr: ast.expr | None) -> int | None:
    """Return the value of `expr` when it is an int constant, else None."""
    if isinstance(expr, ast.Constant) and type(expr.value) is int:
        return expr.value
    return None


def _front_call(
    node: Node, chain: Chain, rebound: frozenset[str], method: str, count: int
) -> bool:
    """Report whether `node` calls `method` with `count` arguments, the first 0, on a carried `LIST` key."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method
        and len(node.args) == count
        and not node.keywords
        and _int_value(node.args[0]) == 0
        and _carried(node.func.value, chain, rebound) == LIST
    )


def _self_assign(node: Node) -> tuple[ast.expr, ast.expr] | None:
    """Return the one target and the value of `node` when it assigns that `_key` from itself."""
    if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
        return None
    target = node.targets[0]
    key = _key(target)
    if key is not None and _derives(node.value, key):
        return target, node.value
    return None


def _pops_front(node: Node, chain: Chain, rebound: frozenset[str]) -> bool:
    """Report whether `node` calls `pop(0)` on a carried list `_key`, or rebinds one to its slice from 1."""
    if _front_call(node, chain, rebound, "pop", 1):
        return True
    assigned = _self_assign(node)
    if assigned is None:
        return False
    target, value = assigned
    return (
        isinstance(value, ast.Subscript)
        and isinstance(value.slice, ast.Slice)
        and (_int_value(value.slice.lower) or 0) >= 1
        and value.slice.upper is None
        and value.slice.step is None
        and _carried(target, chain, rebound) == LIST
    )


def _inserts_front(node: Node, chain: Chain, rebound: frozenset[str]) -> bool:
    """Report whether `node` calls `insert(0, item)` on a carried list `_key`, or rebinds one to a list plus itself."""
    if _front_call(node, chain, rebound, "insert", 2):
        return True
    assigned = _self_assign(node)
    if assigned is None:
        return False
    target, value = assigned
    return (
        isinstance(value, ast.BinOp)
        and isinstance(value.left, ast.List)
        and _key(value.right) == _key(target)
        and _carried(target, chain, rebound) == LIST
    )


def _concatenates(node: Node, chain: Chain, rebound: frozenset[str]) -> bool:
    """Report whether `node` adds to a carried str `_key` by `+=`, or rebinds one to a sum holding itself."""
    if isinstance(node, ast.AugAssign):
        return (
            isinstance(node.op, ast.Add)
            and _carried(node.target, chain, rebound) == STR
        )
    assigned = _self_assign(node)
    return (
        assigned is not None
        and isinstance(assigned[1], ast.BinOp)
        and _carried(assigned[0], chain, rebound) == STR
    )


OWN_RULES: dict[str, OwnRule] = {
    "LOOP001": OwnRule(
        RulePage(
            "list-pop-front-in-loop",
            "none",
            'queue = ["Eric", "John", "Michael"]\n'
            "served: list[str] = []\n"
            "while queue:\n"
            "    served.append(queue.pop(0))\n",
            "from collections import deque\n"
            "\n"
            'queue = deque(["Eric", "John", "Michael"])\n'
            "served: list[str] = []\n"
            "while queue:\n"
            "    served.append(queue.popleft())\n",
        ),
        ((QUEUE_QUOTE, QUEUE_LINK),),
        _pops_front,
    ),
    "LOOP002": OwnRule(
        RulePage(
            "list-insert-front-in-loop",
            "none",
            "queue: list[str] = []\n"
            'for name in ["Eric", "John", "Michael"]:\n'
            "    queue.insert(0, name)\n",
            "from collections import deque\n"
            "\n"
            "queue: deque[str] = deque()\n"
            'for name in ["Eric", "John", "Michael"]:\n'
            "    queue.appendleft(name)\n",
        ),
        ((QUEUE_QUOTE, QUEUE_LINK),),
        _inserts_front,
    ),
    "LOOP003": OwnRule(
        RulePage(
            "str-concat-in-loop",
            "none",
            'words = ["Eric", "John", "Michael"]\n'
            'text = ""\n'
            "for word in words:\n"
            "    text += word\n",
            "import io\n"
            "\n"
            'words = ["Eric", "John", "Michael"]\n'
            "buffer = io.StringIO()\n"
            "for word in words:\n"
            "    buffer.write(word)\n"
            "text = buffer.getvalue()\n",
        ),
        ((CONCAT_QUOTE, CONCAT_LINK),),
        _concatenates,
    ),
}
OWN = hold(OWN_TOOL, tuple(OWN_RULES), DISCIPLINES, CHARACTERISTICS)
CAN_RUN = (
    *(f"{TOOL} {code}" for code in RULES),
    *(f"{OWN.tool} {code}" for code in OWN.rules),
)

SETTINGS: dict[str, str] = {
    "separator": SEPARATOR,
    "ruff_version": RUFF_BUILT,
    **TAKEN.settings(FUNCTION),
    "own_tool": OWN.tool,
    "own_rules": " ".join(OWN.rules),
    "own_reads": "Python's ast module: each own rule fires only inside a part of a "
    "loop that runs on each pass, on a name or attribute the loop carries from pass "
    "to pass, with fix class none",
    "selection": SELECTION,
    "can_run": str(len(CAN_RUN)),
    "fault_file": "the file the input line names: FINDINGS reads HOLD when it sits "
    "in application_source and one of holding_rules fires",
    "ruff_config": "the one ruff finds from the folder of the file",
}


def _ruff_findings(
    source: bytes, folder: Path, rules: tuple[str, ...]
) -> list[tuple[str, int]]:
    """Return each code and line of `rules` for `source` on stdin, run from `folder`; none when `rules` is empty."""
    if not rules:
        return []
    rows = check(source, folder, rules, preview=bool(PREVIEW))
    return [(row.code, row.line) for row in rows]


def _own_findings(source: bytes, codes: tuple[str, ...]) -> list[tuple[str, int]]:
    """Return each code and line where an `OWN_RULES` rule of `codes` matches a node `_repeated` in a loop."""
    if not codes:
        return []
    lines: dict[tuple[str, int], int] = {}
    for loop, chain in _loops(ast.parse(source)):
        rebound = _rebound(loop)
        for node in _walk(_repeated(loop)):
            if not isinstance(node, ast.expr | ast.stmt):
                continue
            for code in codes:
                if OWN_RULES[code].matches(node, chain, rebound):
                    lines[code, id(node)] = node.lineno
    return sorted(
        ((code, line) for (code, _), line in lines.items()),
        key=lambda row: (row[1], row[0]),
    )


def findings(
    text: str, root: Path, to_run: Collection[str]
) -> tuple[str, list[Found]]:
    """Return the ruff version and each `Found` of the `to_run` rules inside the input `text` names."""
    located = locate(text, root)
    if isinstance(located, str):
        message = f"{text}: {located}, after tier 2 accepted it"
        raise ToolFault(message)
    file, source, (first, last) = located
    is_narrowed = bool(text.partition(SETTINGS["separator"])[1])
    rules = tuple(code for code in RULES if f"{TOOL} {code}" in to_run)
    own = tuple(code for code in OWN.rules if f"{OWN.tool} {code}" in to_run)
    read = [
        *(
            Found(TOOL, code, line)
            for code, line in _ruff_findings(source, file.parent, rules)
        ),
        *(Found(OWN.tool, code, line) for code, line in _own_findings(source, own)),
    ]
    found = [item for item in read if not is_narrowed or first <= item.line <= last]
    return f"ruff {ruff_version()}", found


def page(code: str) -> RulePage:
    """Return the `RulePage` of `code`: its `OWN_RULES` page, else the one `rule_page` reads from ruff."""
    rule = OWN_RULES.get(code)
    return rule.page if rule is not None else rule_page(code)


def _source(code: str) -> str:
    """Return the line quoting each of `OWN_RULES` rule `code`'s sources with its link, or nothing for ruff."""
    rule = OWN_RULES.get(code)
    if rule is None:
        return ""
    quoted = "; ".join(f'"{quote}" {link}' for quote, link in rule.sources)
    return f"\n{code} source: {quoted}"


def _content_fault(text: str, root: Path) -> str | None:
    """Return the tier 2 fault of `text`: `locate`'s, else `NO_LOOP`."""
    located = locate(text, root)
    if isinstance(located, str):
        return located
    _, source, (first, last) = located
    has_loop = any(
        isinstance(node, LOOP_NODES) and first <= node.lineno <= last
        for node in ast.walk(ast.parse(source))
    )
    return None if has_loop else NO_LOOP


def _functions_verdict(text: str, root: Path) -> Reading:
    """Return `CLEAN`, or `FINDINGS` holding when a `HOLDING` rule fires, from the `selection` rules."""
    version, found = findings(text, root, selection(text, root, CAN_RUN))
    if not found:
        return Reading(CLEAN, f"{version}: no rule on the list fires", holds=False)
    pages = {item.code: page(item.code) for item in found}
    rows = "; ".join(
        f"{item.code} {pages[item.code].name} line {item.line} fix {pages[item.code].fix}"
        for item in found
    )
    forms = "".join(
        f"{_source(code)}\n{code} faulty:\n{form.faulty}{code} corrected:\n{form.corrected}"
        for code, form in pages.items()
    )
    holds = any(code in HOLDING for code in pages)
    return Reading(FINDINGS, f"{version}: {rows}{forms}", holds)


SIGIL = Sigil(
    name="CODE.LOOP",
    edition=1,
    owner=OWNER,
    disciplines=DISCIPLINES,
    input_form=INPUT_FORM,
    settings=SETTINGS,
    tiers=(
        DATA_TYPE_TIER,
        {
            **CONTENT_TIER,
            "narrowed": "Python's ast module finds a for, async for, while, list, "
            "set or dictionary builder, or generator expression in the input's lines",
            "narrowed_rejects": [NO_LOOP],
        },
        {
            "runs": [
                "the selection: the rules of the card that coding_partition.select "
                "gives for the input's facts; no rule selected, no ruff run",
                (
                    "python -m ruff check --preview --select with the selected rules, "
                    "the file on standard input, from the folder of the file"
                )
                if PREVIEW
                else (
                    "python -m ruff check --select with the selected rules, "
                    "the file on standard input, from the folder of the file"
                ),
                "Python's ast module, for each selected own rule: its form in a part "
                "of a loop that runs on each pass, which is a for or async for body, a "
                "while test or body, or a builder's element, conditions and later "
                "sources; a name, or an attribute of a method's first parameter, is a "
                "list or a str when every binding in its scope, or in its class's "
                "methods, builds one, and the loop carries it when no part run on each "
                "pass assigns it other than by += or from its own value",
                "for a symbol, only the findings inside its lines",
                "python -m ruff rule <code> --output-format json, for each rule "
                "that fires: its name, fix class, and the code under Example, "
                "before and after Use instead",
            ],
            "clean": "no rule on the list fires",
            "findings": [
                "rule id",
                "rule name",
                "line",
                "fix class",
                "for an own rule, each source quoted with its link",
                "faulty form",
                "corrected form",
            ],
            "fix_classes": list(FOLLOW_ON),
            "preview": (
                "the preview_rules fire only with --preview"
                if PREVIEW
                else "no rule on the list is a preview rule, so ruff runs without --preview"
            ),
            "left": TAKEN.left,
            "own_left": OWN.left,
            "left_because": TAKEN.left_because,
            "not_read": "a ruff setting matched on the file name, such as "
            "per-file-ignores, because the file reaches ruff on standard input",
            "refuses": "ruff exits otherwise, or prints a finding or a rule page "
            "this module cannot read",
        },
    ),
    outputs={
        CLEAN: FlagRow(Flag.PASS),
        FINDINGS: FlagRow(Flag.FIX, holds_in_source=bool(HOLDING)),
    },
    refusal=REJECTED,
    follows={
        flag: FLAGS[flag]["follows"] + BY_FIX_CLASS for flag in (Flag.HOLD, Flag.FIX)
    },
    readers=READERS,
    data_type=data_type_fault,
    content=_content_fault,
    functions=_functions_verdict,
    fault_file=fault_file,
)


def loop_check(
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
        print(f"ruff did not run: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())

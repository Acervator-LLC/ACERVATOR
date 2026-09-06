"""JavaScript renderer-module analyzer for `GUIArchetype`.

`tokenize` turns a module into `Token` values, separating code from
strings, template literals, comments and regular expressions. `scan`
resolves the `element(...)` calls those tokens describe into
`ElementCall` values and returns a `RuleFinding` for each screen defect.
`JsParseError` names a source `tokenize` could not finish, and
`GUIArchetype` records it as an error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "COLOUR_LITERAL",
    "INTERACTIVE_TAGS",
    "ElementCall",
    "JsParseError",
    "RuleFinding",
    "Token",
    "element_calls",
    "object_keys",
    "scan",
    "tokenize",
]


class JsParseError(Exception):
    """Raised when `tokenize` reaches the end of a source mid-construct."""


@dataclass(frozen=True)
class Token:
    """One lexical unit of a JavaScript source, with its 1-based line."""

    kind: str
    value: str
    line: int


_ID_START = re.compile(r"[A-Za-z_$]")
_ID_PART = re.compile(r"[A-Za-z0-9_$]")
_NUMBER_START = re.compile(r"[0-9]")

# A regular expression may open only where an operand may not follow.
_REGEX_KEYWORDS: frozenset[str] = frozenset(
    {
        "return",
        "typeof",
        "instanceof",
        "in",
        "of",
        "new",
        "delete",
        "void",
        "do",
        "else",
        "yield",
        "await",
        "case",
        "throw",
    }
)

_VALUE_ENDINGS: frozenset[str] = frozenset(
    {"name", "number", "string", "template", "regex"}
)


def _regex_allowed(previous: Token | None) -> bool:
    if previous is None:
        return True
    if previous.kind in _VALUE_ENDINGS:
        return previous.kind == "name" and previous.value in _REGEX_KEYWORDS
    return previous.value not in (")", "]")


def _read_string(src: str, i: int, line: int) -> tuple[int, int]:
    quote = src[i]
    j = i + 1
    while j < len(src):
        ch = src[j]
        if ch == "\\":
            j += 2
            continue
        if ch == "\n":
            raise JsParseError(f"unterminated string at line {line}")
        if ch == quote:
            return j + 1, line
        j += 1
    raise JsParseError(f"unterminated string at line {line}")


def _read_template(src: str, i: int, line: int) -> tuple[int, int]:
    j = i + 1
    depth = 0
    while j < len(src):
        ch = src[j]
        if ch == "\\":
            j += 2
            continue
        if ch == "\n":
            line += 1
        elif ch == "$" and j + 1 < len(src) and src[j + 1] == "{":
            depth += 1
            j += 2
            continue
        elif ch == "}" and depth:
            depth -= 1
        elif ch == "`" and not depth:
            return j + 1, line
        j += 1
    raise JsParseError(f"unterminated template literal at line {line}")


def _read_regex(src: str, i: int, line: int) -> tuple[int, int]:
    j = i + 1
    in_class = False
    while j < len(src):
        ch = src[j]
        if ch == "\\":
            j += 2
            continue
        if ch == "\n":
            raise JsParseError(f"unterminated regular expression at line {line}")
        if ch == "[":
            in_class = True
        elif ch == "]":
            in_class = False
        elif ch == "/" and not in_class:
            j += 1
            while j < len(src) and _ID_PART.match(src[j]):
                j += 1
            return j, line
        j += 1
    raise JsParseError(f"unterminated regular expression at line {line}")


def tokenize(src: str) -> list[Token]:
    """Return every token of `src`, comments included as kind `comment`.

    Raises `JsParseError` for a string, template literal, regular
    expression or block comment the source never closes.
    """
    tokens: list[Token] = []
    i = 0
    line = 1
    size = len(src)
    previous: Token | None = None
    while i < size:
        ch = src[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        if ch in " \t\r\f\v":
            i += 1
            continue
        start_line = line
        if ch == "/" and i + 1 < size and src[i + 1] == "/":
            end = src.find("\n", i)
            end = size if end == -1 else end
            tokens.append(Token("comment", src[i:end], start_line))
            i = end
            continue
        if ch == "/" and i + 1 < size and src[i + 1] == "*":
            end = src.find("*/", i + 2)
            if end == -1:
                raise JsParseError(f"unterminated block comment at line {start_line}")
            body = src[i : end + 2]
            tokens.append(Token("comment", body, start_line))
            line += body.count("\n")
            i = end + 2
            continue
        if ch == "/" and _regex_allowed(previous):
            i, line = _read_regex(src, i, line)
            previous = Token("regex", "/", start_line)
            tokens.append(previous)
            continue
        if ch in "'\"":
            end, line = _read_string(src, i, line)
            previous = Token("string", src[i:end], start_line)
            tokens.append(previous)
            i = end
            continue
        if ch == "`":
            end, line = _read_template(src, i, line)
            previous = Token("template", src[i:end], start_line)
            tokens.append(previous)
            i = end
            continue
        if _ID_START.match(ch):
            j = i + 1
            while j < size and _ID_PART.match(src[j]):
                j += 1
            previous = Token("name", src[i:j], start_line)
            tokens.append(previous)
            i = j
            continue
        if _NUMBER_START.match(ch):
            j = i + 1
            while j < size and (_ID_PART.match(src[j]) or src[j] == "."):
                j += 1
            previous = Token("number", src[i:j], start_line)
            tokens.append(previous)
            i = j
            continue
        previous = Token("punct", ch, start_line)
        tokens.append(previous)
        i += 1
    return tokens


def _code(tokens: list[Token]) -> list[Token]:
    return [t for t in tokens if t.kind != "comment"]


_OPENERS = frozenset({"(", "[", "{"})
_CLOSERS = frozenset({")", "]", "}"})
_DECLARATORS = frozenset({"var", "const", "let"})


def _split_arguments(tokens: list[Token], open_index: int) -> list[list[Token]] | None:
    """Return the top-level argument runs of the call whose `(` is `open_index`.

    Returns None when `tokens` ends before the matching `)`.
    """
    args: list[list[Token]] = []
    current: list[Token] = []
    depth = 0
    for token in tokens[open_index:]:
        if token.kind == "punct" and token.value in _OPENERS:
            depth += 1
            if depth == 1:
                continue
        elif token.kind == "punct" and token.value in _CLOSERS:
            depth -= 1
            if depth == 0:
                args.append(current)
                return args
        if depth == 1 and token.kind == "punct" and token.value == ",":
            args.append(current)
            current = []
            continue
        current.append(token)
    return None


def _matching_brace(tokens: list[Token], open_index: int) -> int | None:
    depth = 0
    for index in range(open_index, len(tokens)):
        value = tokens[index].value
        if tokens[index].kind != "punct":
            continue
        if value in _OPENERS:
            depth += 1
        elif value in _CLOSERS:
            depth -= 1
            if depth == 0:
                return index
    return None


def string_constants(code: list[Token]) -> dict[str, str]:
    """Return every `var NAME = "text"` binding in `code`, by name.

    A name bound twice to different text is dropped, so `element_calls`
    never resolves a tag the module rebinds.
    """
    found: dict[str, str] = {}
    dropped: set[str] = set()
    for i in range(len(code) - 4):
        if code[i].kind != "name" or code[i].value not in _DECLARATORS:
            continue
        bound, equals, value, after = code[i + 1], code[i + 2], code[i + 3], code[i + 4]
        if bound.kind != "name" or equals.value != "=" or value.kind != "string":
            continue
        if after.value not in (";", ","):
            continue
        text = value.value[1:-1]
        if found.get(bound.value, text) != text:
            dropped.add(bound.value)
        found[bound.value] = text
    for rebound in dropped:
        found.pop(rebound, None)
    return found


_CREATE_ELEMENT = "createElement"


def factory_names(code: list[Token]) -> set[str]:
    """Return every local name in `code` that reaches `React.createElement`.

    Covers `function element(...) { ... createElement ... }` and
    `var h = global.React.createElement`.
    """
    names: set[str] = {_CREATE_ELEMENT}
    for i, token in enumerate(code):
        if token.kind != "name":
            continue
        if (
            token.value == "function"
            and i + 2 < len(code)
            and code[i + 1].kind == "name"
        ):
            open_brace = None
            for j in range(i + 2, min(i + 80, len(code))):
                if code[j].value == "{":
                    open_brace = j
                    break
            if open_brace is None:
                continue
            close = _matching_brace(code, open_brace)
            if close is None:
                continue
            body = code[open_brace:close]
            if any(t.kind == "name" and t.value == _CREATE_ELEMENT for t in body):
                names.add(code[i + 1].value)
            continue
        if (
            token.value in _DECLARATORS
            and i + 2 < len(code)
            and code[i + 1].kind == "name"
        ):
            for j in range(i + 2, min(i + 30, len(code))):
                if code[j].value == ";":
                    break
                if code[j].kind == "name" and code[j].value == _CREATE_ELEMENT:
                    names.add(code[i + 1].value)
                    break
    return names


def object_keys(props: list[Token]) -> dict[str, list[Token]]:
    """Return the top-level `key: value` pairs of an object-literal run.

    An empty mapping answers a run that does not open with `{`.
    """
    if not props or props[0].value != "{":
        return {}
    keys: dict[str, list[Token]] = {}
    depth = 0
    pending: str | None = None
    value: list[Token] = []
    for token in props:
        if token.kind == "punct" and token.value in _OPENERS:
            depth += 1
            if depth == 1:
                continue
        elif token.kind == "punct" and token.value in _CLOSERS:
            depth -= 1
            if depth == 0:
                if pending is not None:
                    keys[pending] = value
                break
        if depth != 1:
            value.append(token)
            continue
        if token.value == ",":
            if pending is not None:
                keys[pending] = value
            pending, value = None, []
            continue
        if token.value == ":" and pending is None and value:
            last = value[-1]
            pending = last.value[1:-1] if last.kind == "string" else last.value
            value = []
            continue
        value.append(token)
    return keys


def _resolve_key(token: Token, consts: dict[str, str]) -> str | None:
    if token.kind == "string":
        return token.value[1:-1]
    if token.kind == "name":
        return consts.get(token.value)
    return None


def props_keys_by_name(
    code: list[Token], consts: dict[str, str]
) -> dict[str, tuple[set[str], bool]]:
    """Return each object variable in `code` with the property names set on it.

    The boolean is False where no `{ ... }` initialiser was seen, leaving
    the starting key set unknown, and `element_calls` declines the call.
    """
    keys: dict[str, set[str]] = {}
    literal_base: set[str] = set()
    for i, token in enumerate(code):
        if token.kind != "name":
            continue
        if (
            token.value in _DECLARATORS
            and i + 3 < len(code)
            and code[i + 1].kind == "name"
            and code[i + 2].value == "="
        ):
            bound = code[i + 1].value
            if code[i + 3].value == "{":
                end = _matching_brace(code, i + 3)
                if end is not None:
                    literal_base.add(bound)
                    keys.setdefault(bound, set()).update(
                        object_keys(code[i + 3 : end + 1])
                    )
            else:
                keys.setdefault(bound, set())
            continue
        if i + 4 < len(code) and code[i + 1].value == "[" and code[i + 3].value == "]":
            if code[i + 4].value != "=" or (
                i + 5 < len(code) and code[i + 5].value == "="
            ):
                continue
            name = _resolve_key(code[i + 2], consts)
            if name is not None:
                keys.setdefault(token.value, set()).add(name)
            continue
        if (
            i + 3 < len(code)
            and code[i + 1].value == "."
            and code[i + 2].kind == "name"
            and code[i + 3].value == "="
            and not (i + 4 < len(code) and code[i + 4].value == "=")
        ):
            keys.setdefault(token.value, set()).add(code[i + 2].value)
    return {name: (found, name in literal_base) for name, found in keys.items()}


def function_spans(code: list[Token]) -> list[tuple[int, int]]:
    """Return the `(open_brace, close_brace)` index pair of each function body.

    `element_calls` reads the innermost span holding a call and resolves
    a props name against that span.
    """
    spans: list[tuple[int, int]] = []
    for i, token in enumerate(code):
        if token.kind != "name" or token.value != "function":
            continue
        for j in range(i + 1, min(i + 80, len(code))):
            if code[j].value == "{":
                end = _matching_brace(code, j)
                if end is not None:
                    spans.append((j, end))
                break
    return spans


def _innermost_span(spans: list[tuple[int, int]], index: int) -> tuple[int, int] | None:
    best: tuple[int, int] | None = None
    for start, end in spans:
        if start < index < end and (best is None or start > best[0]):
            best = (start, end)
    return best


@dataclass(frozen=True)
class ElementCall:
    """One resolved element call: its tag, prop names and child runs."""

    tag: str
    line: int
    prop_names: frozenset[str]
    props_resolved: bool
    children: tuple[tuple[Token, ...], ...]


def element_calls(tokens: list[Token]) -> list[ElementCall]:
    """Return every `element(...)` call whose tag `tokens` resolves to text.

    `props_resolved` is False where the props argument is an expression
    `object_keys` and `props_keys_by_name` cannot read, and every rule
    in `scan` declines such a call.
    """
    code = _code(tokens)
    consts = string_constants(code)
    factories = factory_names(code)
    spans = function_spans(code)
    scoped: dict[tuple[int, int], dict[str, tuple[set[str], bool]]] = {}
    calls: list[ElementCall] = []
    for index, token in enumerate(code):
        if token.kind != "name" or token.value not in factories:
            continue
        if index + 1 >= len(code) or code[index + 1].value != "(":
            continue
        args = _split_arguments(code, index + 1)
        if not args or len(args[0]) != 1:
            continue
        tag = _resolve_key(args[0][0], consts)
        if tag is None:
            continue
        props = args[1] if len(args) > 1 else []
        resolved = True
        names: set[str] = set()
        if not props or (len(props) == 1 and props[0].value == "null"):
            names = set()
        elif props[0].value == "{":
            names = set(object_keys(props))
        elif len(props) == 1 and props[0].kind == "name":
            span = _innermost_span(spans, index)
            if span is None:
                resolved = False
            else:
                if span not in scoped:
                    scoped[span] = props_keys_by_name(code[span[0] : span[1]], consts)
                entry = scoped[span].get(props[0].value)
                if entry is None or not entry[1]:
                    resolved = False
                else:
                    names = set(entry[0])
        else:
            resolved = False
        calls.append(
            ElementCall(
                tag=tag,
                line=token.line,
                prop_names=frozenset(names),
                props_resolved=resolved,
                children=tuple(tuple(a) for a in args[2:] if a),
            )
        )
    return calls


INTERACTIVE_TAGS: frozenset[str] = frozenset(
    {"button", "input", "select", "textarea", "a"}
)

_NAMING_PROPS: frozenset[str] = frozenset(
    {
        "aria-label",
        "aria-labelledby",
        "aria-describedby",
        "title",
        "alt",
        "placeholder",
        "id",
    }
)

_HANDLER_BY_TAG: dict[str, frozenset[str]] = {
    "button": frozenset({"onClick", "onMouseDown", "onKeyDown", "onPointerDown"}),
    "a": frozenset({"onClick", "href"}),
    "input": frozenset(
        {"onChange", "onInput", "onClick", "onKeyDown", "readOnly", "disabled"}
    ),
    "select": frozenset({"onChange", "onInput", "disabled"}),
    "textarea": frozenset({"onChange", "onInput", "readOnly", "disabled"}),
}

COLOUR_LITERAL = re.compile(r"^[\"'](#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6,8}))[\"']$")


@dataclass(frozen=True)
class RuleFinding:
    """One JavaScript screen defect, in the shape `GUIArchetype` emits."""

    tool: str
    severity: str
    file: str
    line: int
    rule_id: str
    message: str


def _scan_elements(path: Path, tokens: list[Token]) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    for call in element_calls(tokens):
        if call.tag not in INTERACTIVE_TAGS or not call.props_resolved:
            continue
        if not (call.prop_names & _NAMING_PROPS) and not call.children:
            findings.append(
                RuleFinding(
                    tool="gui-js",
                    severity="high",
                    file=str(path),
                    line=call.line,
                    rule_id="GUIJS001",
                    message=(
                        f"<{call.tag}> is built with no accessible name and no "
                        f"child content: none of {sorted(_NAMING_PROPS)} is set. "
                        "A screen reader announces the control as unlabelled and "
                        "no test can address it by name."
                    ),
                )
            )
        wanted = _HANDLER_BY_TAG.get(call.tag, frozenset())
        if wanted and not (call.prop_names & wanted):
            findings.append(
                RuleFinding(
                    tool="gui-js",
                    severity="high",
                    file=str(path),
                    line=call.line,
                    rule_id="GUIJS002",
                    message=(
                        f"<{call.tag}> carries none of {sorted(wanted)}; the "
                        "control draws and answers no interaction, so it is inert."
                    ),
                )
            )
    return findings


def _scan_colour_literals(path: Path, tokens: list[Token]) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    for token in _code(tokens):
        if token.kind != "string":
            continue
        match = COLOUR_LITERAL.match(token.value)
        if match is None:
            continue
        findings.append(
            RuleFinding(
                tool="gui-js",
                severity="high",
                file=str(path),
                line=token.line,
                rule_id="GUIJS003",
                message=(
                    f"colour literal {match.group(1)} is written into the module. "
                    "design_tokens.js serves every colour from the Python "
                    "surface, so a literal here is a second source of truth for "
                    "one skin and cannot follow a theme change."
                ),
            )
        )
    return findings


def _scan_absolute_positioning(path: Path, tokens: list[Token]) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    code = _code(tokens)
    for index, token in enumerate(code):
        if token.kind != "string" or token.value[1:-1] != "absolute":
            continue
        if index < 2 or code[index - 1].value != ":":
            continue
        key = code[index - 2]
        name = key.value[1:-1] if key.kind == "string" else key.value
        if name != "position":
            continue
        findings.append(
            RuleFinding(
                tool="gui-js",
                severity="high",
                file=str(path),
                line=token.line,
                rule_id="GUIJS004",
                message=(
                    "position: absolute takes the element out of flow, so the "
                    "screen does not follow a resize or a text-scaling setting."
                ),
            )
        )
    return findings


def scan(path: Path, src: str) -> list[RuleFinding]:
    """Return every screen defect in one JavaScript renderer module.

    Raises `JsParseError` when `tokenize` cannot finish `src`.
    """
    tokens = tokenize(src)
    findings = _scan_elements(path, tokens)
    findings.extend(_scan_colour_literals(path, tokens))
    findings.extend(_scan_absolute_positioning(path, tokens))
    return sorted(findings, key=lambda f: (f.line, f.rule_id))

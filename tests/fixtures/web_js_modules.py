"""How a test runs a ``src/gui/web`` JavaScript module and reads the
values written inside it.

Node is not installed and nothing in this repository adds a JavaScript
test runner. ``QJSEngine`` from ``PySide6.QtQml`` runs a module as plain
JavaScript and answers in JSON instead. ``JsEngine`` wraps one engine
holding one module; a test file subclasses it, names the module file and
the global the module publishes, and adds the methods that module answers.

    from tests.fixtures.web_js_modules import JsEngine, new_engine

    class JsRuntime(JsEngine):
        module_path = MODULE_PATH
        setter = "acervatorSetTokens"

    @pytest.fixture()
    def js(qapp) -> JsRuntime:
        assert qapp is not None
        return JsRuntime(new_engine(), MODULE_PATH.read_text(encoding="utf-8"))

``js_literals`` reports every string, every number and every stray slash
a module writes. A module that publishes a surface's values must carry
none of its own, so a test intersects the reported strings with the
values its surface owns and matches ``HEX_COLOUR`` against the source.
Any ``/`` outside a comment is reported rather than parsed, because a
regular-expression literal could hide a value the scan never reads.

``drain_events`` turns the event loop ``EVENT_DRAIN_ROUNDS`` times so a
promise continuation queued by the module runs before the test reads.

``swap_module`` is how a test puts a changed copy of a shipped module on
disk and puts the original back. It is shared because the module it
writes over is shipped source: a restore that fails quietly leaves the
change in the product, which happened once under ``-n auto``.

FALSIFICATION
=============
Wrong if (a) ``PySide6.QtQml`` is absent, when ``new_engine`` skips and
no runtime check runs at all, (b) a module writes a value inside a
template-literal substitution, which ``js_literals`` reports as one
string and no surface value matches, (c) a subclass declares no
``module_path`` or ``setter``, when construction raises
``AttributeError`` rather than reporting, (d) ``QJSEngine`` gains a
parser its ``evaluate`` accepts and ``js_literals`` does not, when a
literal reaches the module unreported, or (e) ``os.replace`` stops
raising ``PermissionError`` for a held file on Windows, when
``swap_module`` retries nothing and its bound is never reached.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import pytest

HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}")

RENDERER = Path(__file__).resolve().parents[2] / "desktop" / "renderer"

_PAGE_SCRIPT = re.compile(r'src="([^"]+\.js)"')

#: Injects every manifest entry the page has no tag for.
_LOADER = "module_loader.js"


def load_order() -> list:
    """Every module name the renderer runs, in run order.

    Covers both the page's own script tags and the manifest entries
    `module_loader.js` injects, which run at the loader's position.
    """
    from tools import sync_renderer_modules

    page = (RENDERER / "index.html").read_text(encoding="utf-8")
    tags = [src.rsplit("/", 1)[-1] for src in _PAGE_SCRIPT.findall(page)]
    named = sync_renderer_modules.manifest_entries(
        (RENDERER / "module_manifest.js").read_text(encoding="utf-8")
    )
    injected = [name for name in named if name not in tags]
    if not injected:
        return tags
    at = tags.index(_LOADER) + 1 if _LOADER in tags else len(tags)
    return tags[:at] + injected + tags[at:]


#: Attempts before the lock is called stuck.
LOCK_ATTEMPTS = 400_000


@contextlib.contextmanager
def module_lock(path: Path, attempts: int = LOCK_ATTEMPTS):
    """Hold a lock file beside `path` so one worker at a time writes it.

    Built on `os.open` with `O_CREAT | O_EXCL`, which the fast lane's
    package set covers. Raises rather than yielding if `attempts` run out.
    """
    lock = Path(tempfile.gettempdir()) / (path.name + ".acervator.lock")
    handle = None
    for _ in range(attempts):
        # Windows answers a file pending deletion with a permission error.
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except (FileExistsError, PermissionError):
            continue
    if handle is None:
        raise AssertionError(f"{lock} stayed taken for all {attempts} attempts")
    try:
        yield
    finally:
        os.close(handle)
        lock.unlink(missing_ok=True)


def runs_after(order: list, name: str, *needed: str) -> bool:
    """Whether `order` runs `name`, and runs every `needed` name before it.

    False when `name` or any `needed` name is absent from `order`.
    """
    if name not in order:
        return False
    at = order.index(name)
    return all(one in order and order.index(one) < at for one in needed)


EVENT_DRAIN_ROUNDS = 20

#: Windows denies os.replace for as long as another worker reads the module.
SWAP_ATTEMPTS = 2000


def swap_module(
    module_path: Path, content: bytes, attempts: int = SWAP_ATTEMPTS
) -> None:
    """Put ``content`` over ``module_path`` in one atomic ``os.replace``.

    A test appends a value to a shipped ``src/gui/web`` module, scans the
    file back, then calls this again with the original bytes. The write
    goes through a spare file named for this process, so a test in
    another xdist worker reading the module sees either whole file and
    never a half-written one. That open file still denies the replace on
    Windows, so the write is retried up to ``attempts`` times, and the
    bytes that landed are read back and compared. Raises
    ``AssertionError`` naming the module when the attempts run out or
    when the file does not hold ``content`` — a restore that fails
    quietly is what leaves a shipped module edited.
    """
    spare = module_path.with_name(f"{module_path.stem}.swap.{os.getpid()}.tmp")
    for _ in range(attempts):
        try:
            spare.write_bytes(content)
            os.replace(spare, module_path)
            break
        except PermissionError:
            continue
    else:
        spare.unlink(missing_ok=True)
        raise AssertionError(
            f"{module_path.name} was held open for all {attempts} attempts,"
            " so it was left as it was"
        )
    landed = module_path.read_bytes()
    if hashlib.sha256(landed).hexdigest() != hashlib.sha256(content).hexdigest():
        raise AssertionError(
            f"{module_path.name} does not hold the bytes written to it:"
            f" {len(landed)} bytes on disk against {len(content)} written"
        )


def js_literals(source: str) -> dict:
    """Every string and number literal in ``source``, and every stray slash.

    Walks the text once, tracking line comments, block comments and the
    three quote styles. A regular-expression literal could hide a value
    from a scan that does not parse it, so any ``/`` in code that opens
    no comment is reported rather than parsed.
    """
    quotes = "'\"`"
    digits = "0123456789"
    ident = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$")
    numeric = set(digits + ".xXoObBeE_abcdefABCDEF")
    strings: list = []
    numbers: list = []
    slashes: list = []
    index = 0
    end = len(source)
    while index < end:
        char = source[index]
        if char == "/" and source.startswith("//", index):
            stop = source.find("\n", index)
            index = end if stop < 0 else stop + 1
            continue
        if char == "/" and source.startswith("/*", index):
            stop = source.find("*/", index + 2)
            index = end if stop < 0 else stop + 2
            continue
        if char == "/":
            slashes.append(source[max(index - 20, 0) : index + 20])
            index += 1
            continue
        if char in quotes:
            cursor = index + 1
            body: list = []
            while cursor < end and source[cursor] != char:
                if source[cursor] == "\\":
                    body.append(source[cursor : cursor + 2])
                    cursor += 2
                    continue
                body.append(source[cursor])
                cursor += 1
            strings.append("".join(body))
            index = cursor + 1
            continue
        if char in digits and (index == 0 or source[index - 1] not in ident):
            cursor = index
            while cursor < end and source[cursor] in numeric:
                cursor += 1
            numbers.append(source[index:cursor])
            index = cursor
            continue
        index += 1
    return {"strings": strings, "numbers": numbers, "slashes": slashes}


def drain_events() -> None:
    """Let QJSEngine run its promise callbacks.

    Promise continuations are queued as events; without an event loop
    turn they never run and a load test reads its own starting value.
    """
    from PySide6.QtCore import QCoreApplication, QEventLoop

    for _ in range(EVENT_DRAIN_ROUNDS):
        QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)


def new_engine() -> Any:
    """A fresh QJSEngine, or a skip on a host without PySide6.QtQml."""
    return pytest.importorskip("PySide6.QtQml").QJSEngine()


class JsEngine:
    """A QJSEngine holding one ``src/gui/web`` module and a ``window`` global."""

    module_path: Path
    setter: str

    def __init__(self, engine: Any, source: str) -> None:
        self._engine = engine
        engine.evaluate("var window = this;")
        loaded = engine.evaluate(source, self.module_path.name)
        if loaded.isError():
            raise AssertionError(
                self.module_path.name + " did not run: " + loaded.toString()
            )

    def engine_of(self) -> Any:
        """A second engine of the same kind, for a second module body."""
        return type(self._engine)()

    def run(self, script: str) -> Any:
        result = self._engine.evaluate(script)
        assert not result.isError(), script + " -> " + result.toString()
        return result

    def json(self, expression: str) -> Any:
        """Evaluate ``expression`` and bring its value back as Python."""
        text = self.run("JSON.stringify(" + expression + ")").toString()
        return None if text == "undefined" else json.loads(text)

    def bind_json(self, name: str, value: Any) -> None:
        """Set ``name`` on the engine global to ``json.dumps(value)``."""
        self._engine.globalObject().setProperty(name, json.dumps(value))

    def push(self, payload: Any) -> dict:
        """Call ``setter`` with ``payload`` and return what it answers."""
        self.bind_json("PAYLOAD", payload)
        return self.json(self.setter + "(JSON.parse(PAYLOAD))")

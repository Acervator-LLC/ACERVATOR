"""Watchdog archetype — every test pin reaches the one handler.

Operator's design, 2026-08-10:

    "The emitter networks is set up as a network of test points that are
    read as the program runs. They do not receive messages or get
    injected with anything. They are OUTPUT ONLY. Think of the
    application as being a surface with multiple layers and test pins
    stuck in it that are all wired out to the same message handler that
    parses the messages by application subsystem."

    "Coding Archetype builds the emitters and the Watchdog Archetype
    makes sure they work."

So this file has ONE job and no others. The Coding Archetype builds a
pin. This one checks the pin is wired out, so the handler can read it.

WHAT THE WIRE IS
================
`src/core/signal_contract.py` holds one module-level function, `emit`.
It looks up the installed handler and hands the reading to it. Calling
that function IS the wire. There is no other way into the handler.

A pin that calls something else named `emit` -- a local stub, a helper
that writes to a log, a function imported from somewhere else -- records
nothing the handler will ever see. It looks like a working pin in the
source and it is dead in the running program. That is the one defect
this archetype reports.

WHAT IT CHECKS
==============
  W001 (high)  a pin call that does not reach the handler

A call counts as a pin when it is a plain call, not a call on an object,
and its name is `emit`, ends in `_emit`, or is a name this file bound to
`signal_contract.emit` by import or by plain assignment. Bindings are
read from the WHOLE file, because this codebase aliases `emit` INSIDE
the function that uses it -- `_et_emit`, `_cr_emit`, `_tk`, `_dz`,
`_s2`. A matcher that only read module-level imports would see almost
none of the real pins.

WHAT IT DELIBERATELY DOES NOT CHECK
===================================
How a reading is written. The Coding Archetype builds the pins, so the
shape of the call is its job, not this one's.

Whether the pin name starts with a subsystem, so the handler can sort
it. Measured 2026-08-10: all 38 pin names in `src/` already carry one,
across ten subsystems, and none is missing a prefix. A rule that fires
on nothing buys nothing, and the one pin whose name is built at run
time is a name no reader of the source can decide. A badly named
reading still ARRIVES; it just lands in an odd bucket. That is a
naming question, which belongs to the Coding Archetype.

Money values near a pin. That says nothing about whether a pin reports.

EventBus topics. The bus is a separate system that carries payloads
between parts of the program. It is not the pin network, and whether a
topic is declared has no bearing on whether a pin reaches the handler.

`obj.emit(...)` on anything that is not the signal_contract module. Qt
widgets and the EventBus both own an attribute called `.emit` -- 363
such call sites in `src/` -- and reading those as pins reports button
labels as pin names. The cost of that silence is one stated blind spot:
a pin that emits into a `SignalSink` it built for itself, instead of the
installed process handler, is not seen here.

FALSIFICATION
=============
This archetype is wrong if a file calls a bare `emit` that is not
`signal_contract.emit` and the report comes back clean, or if any
finding names a Qt `.emit` or an `EventBus.emit`. Two fixtures under
`docs/audits/2026-08-10_watchdog_archetype/fixtures` hold both sides:
`known_good` must exit 0, `known_bad` must exit 1.
"""
from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from tools.harness.report import ArchetypeReport, Finding, cli_exit

__all__ = ["ArchetypeReport", "Finding", "WatchdogArchetype", "main"]

# --------------------------------------------------------------------- #
# `Finding` and `ArchetypeReport` now live in tools/harness/report.py.
# Five archetypes each carried a copy. The copies drifted, and the
# drift shipped a green report for a run that checked nothing: an
# early return left `findings` empty, and "no high finding" answered
# True. `passed` now also requires that the target was scanned and
# that every required analyzer reported `ok`.
# --------------------------------------------------------------------- #


# --------------------------------------------------------------------- #
# Finding the pins                                                       #
# --------------------------------------------------------------------- #

_SIGNAL_MODULE = "signal_contract"

# The wire itself, and test files that legitimately build stub pins.
_MECHANISM_FILE = "signal_contract.py"


@dataclass
class PinCall:
    """One pin call site and whether it reaches the handler."""
    file: str
    line: int
    callee: str
    wired: bool


class _PinScan(ast.NodeVisitor):
    """Resolve every pin call in one module to wired or not wired."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.calls: list[PinCall] = []
        self.wired_names: set[str] = set()
        self.module_names: set[str] = {_SIGNAL_MODULE}
        # Names bound to an `emit` that came from somewhere OTHER than
        # signal_contract. Still pins by intent, and dead in fact.
        self.pin_names: set[str] = set()

    def collect_bindings(self, tree: ast.AST) -> None:
        """Record every name bound to `signal_contract.emit`.

        Walks the WHOLE tree. Function-local imports are the dominant
        form in this codebase.
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                tail = (node.module or "").rsplit(".", 1)[-1]
                for alias in node.names:
                    if tail == _SIGNAL_MODULE and alias.name == "emit":
                        self.wired_names.add(alias.asname or "emit")
                    elif alias.name == _SIGNAL_MODULE:
                        self.module_names.add(alias.asname or alias.name)
                    elif alias.name == "emit":
                        # `from somewhere_else import emit as _tk`. The
                        # short alias hides the intent from a name-shape
                        # test, so record it here or the dead pin is
                        # invisible. Measured 2026-08-10: every `import
                        # emit` in this tree comes from signal_contract,
                        # so this can only fire on a repointed import.
                        self.pin_names.add(alias.asname or "emit")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.rsplit(".", 1)[-1] == _SIGNAL_MODULE:
                        self.module_names.add(alias.asname or alias.name)
        self._follow_handoffs(tree)

    def _follow_handoffs(self, tree: ast.AST) -> None:
        """Follow `short_name = <a name that is already wired>`.

        A pin can pick up the wire by plain assignment as well as by
        import. Without this, `_ta_emit = emit` reads as a dead pin and
        the report accuses working code. That is the failure that gets
        a gate switched off, so it is worth these few lines.

        Repeats until nothing new appears, because one handoff can feed
        the next.
        """
        assigns = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)]
        grew = True
        while grew:
            grew = False
            for node in assigns:
                val = node.value
                if isinstance(val, ast.Name):
                    from_wire = val.id in self.wired_names
                elif (isinstance(val, ast.Attribute) and val.attr == "emit"
                        and isinstance(val.value, ast.Name)):
                    from_wire = val.value.id in self.module_names
                else:
                    continue
                if not from_wire:
                    continue
                for tgt in node.targets:
                    if not isinstance(tgt, ast.Name):
                        continue
                    if tgt.id not in self.wired_names:
                        self.wired_names.add(tgt.id)
                        grew = True

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        callee: Optional[str] = None
        wired = False
        if isinstance(func, ast.Name):
            # wired_names wins over pin_names on purpose: a file that
            # binds the same name both ways is read as working, because
            # accusing working code is the costlier mistake.
            if func.id in self.wired_names:
                callee, wired = func.id, True
            elif (func.id in self.pin_names or func.id == "emit"
                    or func.id.endswith("_emit")):
                callee, wired = func.id, False
        elif isinstance(func, ast.Attribute) and func.attr == "emit":
            recv = func.value
            head = (recv.id if isinstance(recv, ast.Name)
                    else getattr(recv, "attr", ""))
            # Only `signal_contract.emit(...)`. Every other object that
            # owns `.emit` is a Qt widget or the bus, and neither is a
            # pin.
            if head in self.module_names:
                callee, wired = f"{head}.emit", True
        if callee is not None:
            self.calls.append(
                PinCall(str(self.path), node.lineno, callee, wired))
        self.generic_visit(node)


def _scan_module(path: Path) -> tuple[list[PinCall], Optional[str]]:
    """Return this module's pin calls, or a parse error string."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError, ValueError) as exc:
        return [], f"{path.name}: {type(exc).__name__}: {exc}"
    scan = _PinScan(path)
    scan.collect_bindings(tree)
    scan.visit(tree)
    return scan.calls, None


def is_test_path(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    name = path.name.lower()
    return ("tests" in parts or name.startswith("test_")
            or name.endswith("_test.py") or name == "conftest.py")


def is_exempt(path: Path) -> bool:
    """Files this rule deliberately does not gate.

    A test builds stub pins on purpose, and `signal_contract` IS the
    wire, so neither can be judged against it.
    """
    return is_test_path(path) or path.name == _MECHANISM_FILE


def _iter_python(base: Path) -> list[Path]:
    if base.is_file():
        return [base] if base.suffix == ".py" else []
    return [p for p in sorted(base.rglob("*.py"))
            if "__pycache__" not in p.parts]


# --------------------------------------------------------------------- #
# The archetype                                                          #
# --------------------------------------------------------------------- #


class WatchdogArchetype:
    """Checks one thing: every test pin is wired out to the handler."""

    name = "watchdog"
    version = "2.0"
    tools = ("pin-wiring",)

    def review(self, target: Path) -> ArchetypeReport:
        target = Path(target).resolve()
        rep = ArchetypeReport(target=str(target))
        if not target.exists():
            rep.tool_availability["pin-wiring"] = "error"
            rep.errors.append(f"target not found: {target}")
            rep.falsification = self._falsification(0, 0, 0)
            return rep

        # Past this line the scan actually runs over the target.
        # `scanned` stays False on the early return above, so an
        # empty report can no longer answer passed=True.
        rep.scanned = True
        gated = [p for p in _iter_python(target) if not is_exempt(p)]
        calls: list[PinCall] = []
        unscanned = 0
        for path in gated:
            found, err = _scan_module(path)
            if err:
                rep.errors.append(err)
                unscanned += 1
                continue
            calls.extend(found)
        # A module that would not parse was DROPPED from the scan, and
        # every pin inside it with it. "0 unwired pins" over a set that
        # silently lost a file is not a measurement. MEASURED 2026-08-13
        # on a directory holding one unparseable module: exit 0,
        # passed=True, pin-wiring `ok`, and the SyntaxError sitting
        # unread in `errors`.
        rep.tool_availability["pin-wiring"] = (
            "error" if unscanned else "ok")

        for call in calls:
            if call.wired:
                continue
            rep.findings.append(Finding(
                tool="pin-wiring", severity="high", file=call.file,
                line=call.line, rule_id="W001",
                message=(
                    f"`{call.callee}(...)` is a pin that does not reach the "
                    f"handler. Only `emit` from src/core/signal_contract.py "
                    f"hands a reading to the installed sink; this name is "
                    f"not bound to it anywhere in this file, so the reading "
                    f"goes nowhere and nothing downstream can see it. A pin "
                    f"that reports into nothing is indistinguishable from a "
                    f"pin nobody wrote. Import it: "
                    f"`from src.core.signal_contract import emit`.")))

        wired = sum(1 for c in calls if c.wired)
        rep.falsification = self._falsification(
            len(gated), wired, len(calls) - wired)
        return rep

    @staticmethod
    def _falsification(files: int, wired: int, unwired: int) -> str:
        return (
            f"Pins seen: {wired} wired, {unwired} not wired, over {files} "
            f"file(s) scanned. A zero here is a claim about the code only "
            f"if pins were found; if the wired count is 0 the target holds "
            f"no pins and this report says nothing about wiring. This "
            f"report is wrong if: (a) the target calls a bare `emit` that "
            f"is not signal_contract's and no finding names it; (b) any "
            f"finding names a Qt pyqtSignal.emit or an EventBus.emit -- "
            f"three mechanisms share the attribute `.emit` in this tree and "
            f"only one is a pin; (c) either fixture in "
            f"docs/audits/2026-08-10_watchdog_archetype/fixtures stops "
            f"discriminating, known_good exiting non-zero or known_bad "
            f"exiting zero.")


# --------------------------------------------------------------------- #
# CLI                                                                    #
# --------------------------------------------------------------------- #


def main(argv: Optional[list[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: python -m tools.harness.watchdog_archetype <path>")
        print("       checks every test pin is wired out to the handler")
        print("       in src/core/signal_contract.py;")
        print("       prints JSON report; exit 0 if passed, 1 if failed")
        return 2
    report = WatchdogArchetype().review(Path(argv[0]))
    print(json.dumps(report.to_dict(), indent=2))
    return cli_exit(report)


if __name__ == "__main__":
    sys.exit(main())

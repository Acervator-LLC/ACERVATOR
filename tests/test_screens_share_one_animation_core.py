"""No presentation screen may re-grow a private copy of a shared helper.

WHAT THIS GUARDS
================
Issue #74 reported that ``splash_screen.py``, ``cartoon_screen.py`` and
``investor_screen.py`` each carried their own copy of the same private
animation API: a smoothstep ease, a scene-alpha envelope, an alpha
clamp, a colour helper, a blurred-text-halo builder with its cache, a
grid loop, a scanline loop, a tag label and a timer tick. The three
copies had already drifted: one had a divide-by-zero guard the others
did not, one drew its tag 2 px taller than the others, and the fade
defaults disagreed in all three. That drift is what a shared core stops,
and it is what comes back if a screen quietly redefines one of these
again.

``screen_fx.AnimatedScreenBase`` now holds the shared implementations.

THE INSTRUMENT
==============
Issue #87 measured the failure mode this file must avoid: a parity test
that compared two functions BY NAME stayed green while their bodies
diverged completely. Nothing here compares names to names. Each rule
reads a BODY:

1. ``test_no_screen_redefines_a_base_method`` reads the method names
   from ``AnimatedScreenBase`` itself, not from a list written here, and
   fails if a screen defines any of them. There is no allowlist: the
   per-screen adapters are deliberately named apart from the base
   methods they call (``_glow`` and ``_glow_text`` call ``_draw_glow``;
   ``_tag`` calls ``_draw_tag``; ``_bg`` and ``_grid`` call
   ``_draw_grid``), so an allowlist would only be a place to hide a
   regression.

2. ``test_no_screen_repeats_a_shared_body`` unparses every function in
   ``screen_fx`` and every function in each screen, and fails when a
   screen's function body is the shared one. This is the rule that a
   name comparison cannot make.

3. ``test_each_screen_is_an_animated_screen`` stops rule 1 from going
   vacuous. A screen that stopped inheriting the base would pass rule 1
   by having no base methods to redefine.

4. ``test_the_shared_accents_are_what_the_screens_use`` pins the eight
   colours the screens agreed on, so a screen cannot fork the palette
   back out by editing the numbers.

These tests parse files and read one imported module. They build no
widget and need no QApplication.

TWO-SIDED
=========
``TestTheRulesFire`` drives every rule with a synthetic module that
carries the defect the rule exists for. No rule here is asserted only in
the passing direction.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SHARED = "screen_fx.py"
SCREENS = ("splash_screen.py", "cartoon_screen.py", "investor_screen.py")
SCREEN_CLASSES = {
    "splash_screen.py": "SplashScreen",
    "cartoon_screen.py": "CartoonScreen",
    "investor_screen.py": "InvestorScreen",
}


def _tree(name: str) -> ast.Module:
    return ast.parse((REPO_ROOT / name).read_text(encoding="utf-8"), filename=name)


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    """Every function and method in the module, by name.

    Nested helpers are included on purpose. Two screens defined local
    ``tx`` and ``ty`` chart-mapping closures, and a shared body could be
    hidden inside one just as easily as at the top level.
    """
    out: dict[str, ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            out[node.name] = node
    return out


def _body_text(node: ast.FunctionDef) -> str:
    """The statements of a function, unparsed, with the docstring gone.

    The signature is dropped: an adapter that keeps a screen's own
    parameter list is not the thing this file hunts. The docstring is
    dropped so prose cannot make two identical bodies read as different.
    """
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return "\n".join(ast.unparse(stmt) for stmt in body).strip()


def _is_dunder(name: str) -> bool:
    """True for a name the language itself owns, such as ``__init__``.

    Overriding one of those is how subclassing works, not a copy of a
    helper. Each screen builds itself differently -- splash parents a
    frameless always-on-top window on a target window, the other two
    take a plain parent -- so each keeps its own ``__init__``. The
    exclusion is by MECHANISM: no name is listed, so nothing that is not
    a language protocol name can hide behind it.
    """
    return name.startswith("__") and name.endswith("__")


def _base_method_names() -> set[str]:
    """The helper names AnimatedScreenBase defines, read from the class."""
    import screen_fx

    return {
        name
        for name, value in vars(screen_fx.AnimatedScreenBase).items()
        if inspect.isfunction(value) and not _is_dunder(name)
    }


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------


def test_the_shared_module_is_not_in_a_directory_the_build_ships() -> None:
    """``screen_fx.py`` must not travel into every frozen application.

    ``tools/spec_common.datas_candidates`` copies the WHOLE ``src`` and
    ``resources`` directories into the build. Issue #74 proposed
    ``src/gui/screen_fx.py``. Nothing in the application imports these
    screens, so at the repository root the module ships in NO build.
    """
    from tools.spec_common import datas_candidates

    shipped = {Path(source).name for source, _dest in datas_candidates(str(REPO_ROOT))}
    assert {"src", "resources"} <= shipped, (
        f"the spec no longer ships src and resources wholesale "
        f"({sorted(shipped)}); this rule's premise has changed and the "
        f"rule needs rewriting, not deleting"
    )

    assert (REPO_ROOT / SHARED).is_file(), f"{SHARED} is not at the root"
    stowaways = [
        f"{d}/**/{SHARED}"
        for d in ("src", "resources")
        if any((REPO_ROOT / d).rglob(SHARED))
    ]
    assert stowaways == [], (
        f"the shared animation core is under a directory the build ships "
        f"wholesale: {stowaways}. The three screens it serves ship in no "
        f"build; there it would be dead weight in every release"
    )


@pytest.mark.parametrize("name", SCREENS)
def test_each_screen_is_an_animated_screen(name: str) -> None:
    """Without this, the redefinition rule below has nothing to compare.

    A screen that stopped inheriting ``AnimatedScreenBase`` would define
    every helper again and still pass a rule that only asks whether a
    base method was overridden.
    """
    import screen_fx

    module = __import__(name[:-3])
    cls = getattr(module, SCREEN_CLASSES[name])
    assert issubclass(
        cls, screen_fx.AnimatedScreenBase
    ), f"{SCREEN_CLASSES[name]} no longer inherits AnimatedScreenBase"
    assert cls.TOTAL_DURATION == module.TOTAL_DURATION, (
        f"{name} sets a class TOTAL_DURATION that disagrees with its "
        f"module constant; mousePressEvent reads the class one"
    )


@pytest.mark.parametrize("name", SCREENS)
def test_no_screen_redefines_a_base_method(name: str) -> None:
    """A shared helper re-declared on a screen is a private copy again."""
    shared_names = _base_method_names()
    assert shared_names, "AnimatedScreenBase defines no methods to check"
    offenders = sorted(set(_functions(_tree(name))) & shared_names)
    assert offenders == [], (
        f"{name} defines {offenders}, which AnimatedScreenBase already "
        f"provides. Call the base method, or if the screen truly needs "
        f"different behaviour, give the override a name of its own and "
        f"say in one line what differs"
    )


@pytest.mark.parametrize("name", SCREENS)
def test_no_screen_repeats_a_shared_body(name: str) -> None:
    """A body copied out of ``screen_fx`` is the duplication returning.

    Bodies, not names. Issue #87 measured a parity test that compared
    two functions by name and stayed green while the bodies diverged
    completely; the mirror-image failure is a body that comes back under
    a new name and is never noticed.
    """
    shared_bodies = {
        _body_text(fn): fn_name
        for fn_name, fn in _functions(_tree(SHARED)).items()
        if _body_text(fn)
    }
    assert len(shared_bodies) > 5, (
        f"only {len(shared_bodies)} bodies were read out of {SHARED}; "
        f"the instrument cannot report a copy it never loaded"
    )

    copies = [
        f"{name}:{fn_name} repeats {SHARED}:{shared_bodies[body]}"
        for fn_name, fn in _functions(_tree(name)).items()
        if (body := _body_text(fn)) in shared_bodies
    ]
    assert copies == [], (
        f"{copies}. The shared implementation lives in {SHARED}; a "
        f"second copy is what issue #74 removed"
    )


def test_the_shared_accents_are_what_the_screens_use() -> None:
    """The eight colours the three screens agreed on, pinned by value.

    A screen that edited one of these numbers back into a local literal
    would change what it draws, and nothing else would say so.
    """
    import screen_fx

    assert screen_fx.RGB == {
        "cy": (0, 255, 238),
        "gn": (0, 255, 136),
        "mg": (255, 0, 170),
        "bl": (0, 170, 255),
        "or": (255, 170, 0),
        "rd": (255, 51, 85),
        "wh": (216, 232, 255),
        "mu": (136, 153, 187),
    }

    import cartoon_screen
    import investor_screen
    import splash_screen

    for key, screen_const in (
        ("cy", splash_screen.CYAN),
        ("gn", splash_screen.GREEN),
        ("mg", splash_screen.MAGENTA),
        ("bl", splash_screen.BLUE),
        ("or", splash_screen.ORANGE),
        ("mu", splash_screen.MUTED),
    ):
        assert screen_const.getRgb()[:3] == screen_fx.RGB[key], key

    for module in (cartoon_screen, investor_screen):
        for key, rgb in screen_fx.RGB.items():
            assert module.C[key].getRgb()[:3] == rgb, (module.__name__, key)


def test_the_palette_hands_out_no_shared_qcolor_instance() -> None:
    """A QColor is mutable, so one shared instance is one shared defect.

    ``setAlpha`` writes in place. If the two screens held the SAME
    QColor for an accent, one screen fading that accent would fade it in
    the other.
    """
    import cartoon_screen
    import investor_screen
    import screen_fx

    assert screen_fx.colour("cy") is not screen_fx.colour("cy")
    for key in screen_fx.RGB:
        assert cartoon_screen.C[key] is not investor_screen.C[key], key


# ---------------------------------------------------------------------------
# Two-sided: each rule, driven with the case it exists for
# ---------------------------------------------------------------------------


class TestTheRulesFire:
    """A rule that is never shown failing is a rule nobody has tested."""

    def test_a_redefined_base_method_is_reported(self) -> None:
        pretend = ast.parse("class S:\n" "    def _a(self, v):\n" "        return 0\n")
        offenders = sorted(set(_functions(pretend)) & _base_method_names())
        assert offenders == ["_a"]

    def test_a_dunder_override_is_not_reported(self) -> None:
        """``__init__`` is the language's, and every screen keeps its own."""
        import screen_fx

        assert "__init__" in vars(screen_fx.AnimatedScreenBase), (
            "AnimatedScreenBase no longer defines __init__, so this "
            "control proves nothing"
        )
        pretend = ast.parse("class S:\n" "    def __init__(self):\n" "        pass\n")
        assert set(_functions(pretend)) & _base_method_names() == set()

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("__init__", True),
            ("__repr__", True),
            ("_a", False),
            ("_tick", False),
            ("_draw_glow", False),
            ("__private", False),
            ("dunder__", False),
        ],
    )
    def test_the_dunder_rule_reads_the_name(self, name: str, expected: bool) -> None:
        """The exclusion must not widen into one that hides a helper."""
        assert _is_dunder(name) is expected

    def test_a_screen_that_redefines_nothing_is_not_reported(self) -> None:
        pretend = ast.parse(
            "class S:\n"
            "    def _glow(self, p):\n"
            "        return self._draw_glow(p)\n"
        )
        assert set(_functions(pretend)) & _base_method_names() == set()

    def test_a_copied_body_is_reported(self) -> None:
        """The real shared body, pasted into a synthetic screen."""
        import textwrap

        shared = _functions(_tree(SHARED))["smoothstep"]
        pasted = ast.parse(
            "def totally_different_name(x):\n"
            + textwrap.indent(_body_text(shared), "    ")
            + "\n"
        )
        shared_bodies = {
            _body_text(fn): fn_name
            for fn_name, fn in _functions(_tree(SHARED)).items()
            if _body_text(fn)
        }
        copies = [
            fn_name
            for fn_name, fn in _functions(pasted).items()
            if _body_text(fn) in shared_bodies
        ]
        assert copies == ["totally_different_name"], (
            "the body search did not find a body copied verbatim out of "
            "screen_fx under a new name"
        )

    def test_a_body_that_is_not_shared_is_not_reported(self) -> None:
        pretend = ast.parse("def f(x):\n    return x + 1\n")
        shared_bodies = {
            _body_text(fn)
            for fn in _functions(_tree(SHARED)).values()
            if _body_text(fn)
        }
        assert [
            n
            for n, fn in _functions(pretend).items()
            if _body_text(fn) in shared_bodies
        ] == []

    def test_the_docstring_is_not_what_makes_two_bodies_differ(self) -> None:
        """Prose must not be able to disguise a copy."""
        with_doc = ast.parse('def f(x):\n    """words"""\n    return x\n')
        without = ast.parse("def g(x):\n    return x\n")
        assert _body_text(_functions(with_doc)["f"]) == _body_text(
            _functions(without)["g"]
        )

    def test_the_stowaway_search_finds_a_real_file(self) -> None:
        """Positive control for the build-sweep rule.

        The search reports an empty list. An empty list is a claim about
        the instrument until the instrument is shown finding something.
        """
        assert list((REPO_ROOT / "src").rglob("__init__.py"))

    def test_the_base_class_actually_holds_the_shared_helpers(self) -> None:
        """Positive control for every rule that reads the base class."""
        names = _base_method_names()
        for expected in (
            "_a",
            "_c",
            "_tick",
            "_txt",
            "_hline",
            "_make_glow_px",
            "_draw_glow",
            "_draw_grid",
            "_draw_scanlines",
            "_draw_tag",
            "mousePressEvent",
        ):
            assert expected in names, f"{expected} left AnimatedScreenBase"

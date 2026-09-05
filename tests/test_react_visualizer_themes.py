"""Issue #128 Stage 3 -- the React side of the visualizer themes.

WHAT IS PROVED
==============
``src/gui/web/visualizer_themes.js`` publishes the four canvas themes
and four tier palettes ``src/gui/main_tabs/visualizer_themes_surface.py``
serves, and carries no theme, tier or threshold value of its own.

Five defect classes are pinned directly:

1. ``channels`` and ``rgbaText`` split a colour red first, the CSS
   order the surface documents -- never Qt's alpha-first order.
2. ``tierAnswer`` walks the ceilings in the order they arrived, which a
   test proves by shuffling that order in a planted payload.
3. Every bag this module reads is keyed by words, so a browser holding
   integer-like keys in ascending order rather than insertion order
   cannot silently reorder anything here -- proved directly.
4. The module never places a non-finite number in an outgoing bridge
   call, which would corrupt the whole frame.
5. ``hasTheme``/``hasTier`` tell a name the surface never held apart
   from a name that answered with every value blank.

HOW THE JAVASCRIPT IS RUN
==========================
Node is not installed. ``QJSEngine`` runs the module as plain
JavaScript and answers in JSON; ``QWebEngineView`` loads the real
``desktop/renderer/index.html`` to prove the module runs under the
page's own content-security policy.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import visualizer_themes_surface as surface
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    drain_events,
    js_literals,
    load_order,
    new_engine,
    runs_after,
)

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "visualizer_themes.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

JS_TIMEOUT_MS = 30_000

FIRST_THEME = surface.THEME_NAMES[0]
SECOND_THEME = surface.THEME_NAMES[1]
FIRST_TIER = surface.TIER_NAMES[0]
SECOND_TIER = surface.TIER_NAMES[1]
FIRST_THEME_COLOUR_FIELD = surface.THEME_COLOUR_FIELDS[0]
FIRST_TIER_COLOUR_FIELD = surface.TIER_COLOUR_FIELDS[0]

#: Constants a hex splitter and an array index need; ``"9a"`` is a scanner artefact.
ALGORITHM_NUMBERS = {"0", "1", "2", "3", "4", "6", "8", "16", "255", "9a"}


def bridge_payload(**params: Any) -> dict:
    """The surface's answer after one round trip through the bridge's JSON."""
    return json.loads(json.dumps(surface.build_view_model(**params), ensure_ascii=True))


# -- the JavaScript engine ----------------------------------------------


class JsRuntime(JsEngine):
    module_path = MODULE_PATH
    setter = "acervatorSetVisualizerThemes"

    def theme_values(self, name: str) -> dict:
        self.bind_json("NAME", name)
        return self.json("acervatorVisualizerThemes.themeColours(JSON.parse(NAME))")

    def tier_values(self, name: str) -> dict:
        self.bind_json("NAME", name)
        return self.json("acervatorVisualizerThemes.tierColours(JSON.parse(NAME))")

    def channels(self, colour: str) -> Any:
        self.bind_json("COLOUR", colour)
        return self.json("acervatorVisualizerThemes.channels(JSON.parse(COLOUR))")

    def tier_answer(self, balance: Any) -> Any:
        self.bind_json("BALANCE", balance)
        return self.json("acervatorVisualizerThemes.tierAnswer(JSON.parse(BALANCE))")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_PATH.read_text(encoding="utf-8"))


@pytest.fixture()
def loaded(js: JsRuntime) -> JsRuntime:
    """The module holding the real surface's whole answer, no name asked."""
    js.push(bridge_payload())
    return js


# -- 1. every theme and every tier reaches the JavaScript side ----------


def test_the_module_holds_every_theme_the_surface_publishes(loaded: JsRuntime):
    surface_names = sorted(surface.THEME_NAMES)
    module_names = sorted(loaded.json("acervatorVisualizerThemes.themeNames()"))
    assert module_names == surface_names


def test_the_theme_reach_check_names_a_theme_only_the_surface_holds(js: JsRuntime):
    """The control. Without it a module that dropped a theme reads as agreement."""
    payload = bridge_payload()
    del payload["themes"][FIRST_THEME]
    js.push(payload)
    missing = set(surface.THEME_NAMES) - set(
        js.json("acervatorVisualizerThemes.themeNames()")
    )
    assert missing == {FIRST_THEME}


def test_the_module_holds_every_tier_the_surface_publishes(loaded: JsRuntime):
    surface_names = sorted(surface.TIER_NAMES)
    module_names = sorted(loaded.json("acervatorVisualizerThemes.tierNames()"))
    assert module_names == surface_names


def test_the_tier_reach_check_names_a_tier_only_the_surface_holds(js: JsRuntime):
    """The control for the tier count."""
    payload = bridge_payload()
    del payload["tier_palettes"][FIRST_TIER]
    js.push(payload)
    missing = set(surface.TIER_NAMES) - set(
        js.json("acervatorVisualizerThemes.tierNames()")
    )
    assert missing == {FIRST_TIER}


def test_every_value_of_every_theme_agrees_with_the_surface(loaded: JsRuntime):
    expected = bridge_payload()["themes"]
    checked = 0
    for name, values in expected.items():
        actual = loaded.theme_values(name)
        differing = {
            f: (values[f], actual.get(f)) for f in values if actual.get(f) != values[f]
        }
        assert not differing, f"{name}: {differing}"
        assert len(actual) == len(values)
        checked += len(values)
    assert checked == len(surface.THEME_NAMES) * len(surface.THEME_FIELD_NAMES)


def test_the_theme_value_check_names_a_changed_value(js: JsRuntime):
    """The control. Two payloads differing by one value must not compare equal."""
    payload = bridge_payload()
    payload["themes"][FIRST_THEME][FIRST_THEME_COLOUR_FIELD] = "#11223344"
    js.push(payload)
    actual = js.theme_values(FIRST_THEME)
    assert actual[FIRST_THEME_COLOUR_FIELD] == "#11223344"
    assert (
        actual[FIRST_THEME_COLOUR_FIELD]
        != surface.THEMES[FIRST_THEME][FIRST_THEME_COLOUR_FIELD]
    )


def test_every_value_of_every_tier_agrees_with_the_surface(loaded: JsRuntime):
    expected = bridge_payload()["tier_palettes"]
    for name, values in expected.items():
        actual = loaded.tier_values(name)
        differing = {
            f: (values[f], actual.get(f)) for f in values if actual.get(f) != values[f]
        }
        assert not differing, f"{name}: {differing}"
        assert len(actual) == len(values)


def test_the_display_names_agree_with_the_surface(loaded: JsRuntime):
    for key, shown in surface.DISPLAY_NAMES.items():
        loaded.bind_json("K", key)
        assert (
            loaded.json("acervatorVisualizerThemes.themeDisplayName(JSON.parse(K))")
            == shown
        )
    for key, shown in surface.TIER_DISPLAY_NAMES.items():
        loaded.bind_json("K", key)
        assert (
            loaded.json("acervatorVisualizerThemes.tierDisplayName(JSON.parse(K))")
            == shown
        )


def test_the_ceilings_and_top_tier_agree_with_the_surface(loaded: JsRuntime):
    assert loaded.json("acervatorVisualizerThemes.ceilings()") == dict(
        surface.TIER_CEILINGS_USD
    )
    assert loaded.json("acervatorVisualizerThemes.topTier()") == surface.TOP_TIER


# -- 2. no theme, tier or threshold is written in the JavaScript --------


def surface_values() -> set:
    """Every colour, display name and threshold the surface owns as text."""
    found = {str(v) for row in surface.THEMES.values() for v in row.values()}
    found.update(str(v) for row in surface.TIER_PALETTES.values() for v in row.values())
    found.update(str(v) for v in surface.TIER_CEILINGS_USD.values())
    found.add(surface.TOP_TIER)
    return found


@pytest.fixture(scope="module")
def module_source() -> str:
    return MODULE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def module_literals(module_source: str) -> dict:
    return js_literals(module_source)


def test_the_module_writes_no_colour(module_source: str):
    found = HEX_COLOUR.findall(module_source)
    assert not found, f"visualizer_themes.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_surface_value(module_literals: dict):
    written = sorted(set(module_literals["strings"]) & surface_values())
    assert not written, f"visualizer_themes.js spells out surface values: {written}"


def test_every_number_the_module_writes_is_an_algorithm_constant(module_literals: dict):
    """A number outside byte-slicing arithmetic is a value the surface should own."""
    stray = sorted(set(module_literals["numbers"]) - ALGORITHM_NUMBERS)
    assert not stray, f"visualizer_themes.js holds unexplained numbers: {stray}"


#: Every ``/`` the scan can find outside a comment: both delimiters of
#: the two parsing regexes, and the one division in ``rgbaText``.
KNOWN_SLASH_MARKERS = ("0-9a-fA-F", "replace(/^#+/", "parts[3] / 255")


def test_the_module_hides_no_value_behind_a_regular_expression(module_literals: dict):
    """Every bare slash is named, so a value hidden in one would be caught."""
    assert len(module_literals["slashes"]) == 5, module_literals["slashes"]
    for snippet in module_literals["slashes"]:
        assert any(marker in snippet for marker in KNOWN_SLASH_MARKERS), snippet


def test_the_literal_scan_names_a_planted_colour():
    """The control for the colour check."""
    planted = 'var x = "#00ffcc";'
    assert HEX_COLOUR.findall(planted) == ["#00ffcc"]
    assert "#00ffcc" in js_literals(planted)["strings"]


def test_the_literal_scan_names_a_planted_surface_value():
    """The control for the value check."""
    planted = 'var x = "' + surface.THEMES[FIRST_THEME][FIRST_THEME_COLOUR_FIELD] + '";'
    strings = set(js_literals(planted)["strings"])
    assert strings & surface_values() == {
        surface.THEMES[FIRST_THEME][FIRST_THEME_COLOUR_FIELD]
    }


def test_the_literal_scan_names_a_stray_number():
    """The control for the number check."""
    found = js_literals("var x = 4913;")["numbers"]
    assert found == ["4913"]
    assert set(found) - ALGORITHM_NUMBERS == {"4913"}


# -- 3. defect 1: colour order is red first, never Qt's alpha-first -----


@pytest.mark.parametrize(
    "colour,expected",
    [
        ("#3c287828", [60, 40, 120, 40]),
        ("#ffffffff", [255, 255, 255, 255]),
        ("#00000000", [0, 0, 0, 0]),
    ],
)
def test_channels_splits_red_first(js: JsRuntime, colour, expected):
    assert js.channels(colour) == expected
    assert list(surface.channels(colour)) == expected


def test_channels_agrees_with_the_surface_for_every_real_colour(loaded: JsRuntime):
    for name in surface.THEME_NAMES:
        for field in surface.THEME_COLOUR_FIELDS:
            colour = surface.THEMES[name][field]
            assert loaded.channels(colour) == list(surface.channels(colour)), (
                name,
                field,
            )
    for name in surface.TIER_NAMES:
        for field in surface.TIER_COLOUR_FIELDS:
            colour = surface.TIER_PALETTES[name][field]
            assert loaded.channels(colour) == list(surface.channels(colour)), (
                name,
                field,
            )


def test_channels_refuses_a_short_colour(js: JsRuntime):
    """The control for the malformed-colour guard: a short string is refused."""
    js.bind_json("COLOUR", "#112233")
    result = js.run(
        "(function () {"
        "  try { acervatorVisualizerThemes.channels(JSON.parse(COLOUR)); return 'answered'; }"
        "  catch (e) { return 'refused'; } })()"
    )
    assert result.toString() == "refused"


def test_rgba_text_never_puts_alpha_first(js: JsRuntime):
    """Qt reads eight hex digits alpha first; a caller reading this text must not."""
    js.bind_json("COLOUR", "#3c287828")
    text = js.json("acervatorVisualizerThemes.rgbaText(JSON.parse(COLOUR))")
    assert text == "rgba(60, 40, 120, " + str(40 / 255) + ")"
    assert not text.startswith("rgba(40")


def test_the_theme_channels_the_surface_precomputed_agree_with_a_fresh_parse(
    loaded: JsRuntime,
):
    for field in surface.THEME_COLOUR_FIELDS:
        loaded.bind_json("NAME", FIRST_THEME)
        loaded.bind_json("FIELD", field)
        precomputed = loaded.json(
            "acervatorVisualizerThemes.themeChannelsFor(JSON.parse(NAME), JSON.parse(FIELD))"
        )
        colour = surface.THEMES[FIRST_THEME][field]
        assert precomputed == list(surface.channels(colour)), field


# -- 4. defect 2 and 3: ceiling order is preserved, not resorted --------


def test_json_parse_keeps_the_word_keyed_ceiling_order(js: JsRuntime):
    """The ceilings are word-keyed, so V8 must not resort them numerically."""
    js.bind_json("PAYLOAD", bridge_payload())
    keys = js.json("Object.keys(JSON.parse(PAYLOAD).tier_ceilings_usd)")
    assert keys == list(surface.TIER_CEILINGS_USD)


def test_tier_answer_walks_the_ceilings_in_the_order_they_arrived(js: JsRuntime):
    """A shuffled payload proves the walk follows the given order, not a memorised one."""
    payload = bridge_payload()
    payload["tier_ceilings_usd"] = {"bumper": 10_000, "harvest": 100, "great": 1_000}
    js.push(payload)
    js.bind_json("BALANCE", 500)
    assert js.tier_answer(500) == ["bumper", ""]


def test_tier_answer_matches_the_surface_for_the_real_ceiling_order(loaded: JsRuntime):
    for balance in (0, 99.99, 100, 999.99, 1_000, 9_999.99, 10_000, 50_000):
        assert loaded.tier_answer(balance) == [
            surface.tier_for_target_balance(balance),
            "",
        ]


def test_tier_answer_matches_the_surface_on_not_a_number(loaded: JsRuntime):
    """``NaN`` is a JS keyword, not JSON, so it is sent as a raw expression."""
    answer = loaded.json("acervatorVisualizerThemes.tierAnswer(NaN)")
    assert answer[0] == surface.tier_for_target_balance(math.nan)
    assert answer[0] == surface.TOP_TIER


def test_tier_answer_matches_the_surface_on_infinity(loaded: JsRuntime):
    assert loaded.json("acervatorVisualizerThemes.tierAnswer(Infinity)") == [
        surface.tier_for_target_balance(float("inf")),
        "",
    ]
    assert loaded.json("acervatorVisualizerThemes.tierAnswer(-Infinity)") == [
        surface.tier_for_target_balance(float("-inf")),
        "",
    ]


def test_tier_answer_matches_the_surface_on_a_boolean(loaded: JsRuntime):
    assert loaded.json("acervatorVisualizerThemes.tierAnswer(true)") == [
        surface.tier_for_target_balance(True),
        "",
    ]
    assert loaded.json("acervatorVisualizerThemes.tierAnswer(false)") == [
        surface.tier_for_target_balance(False),
        "",
    ]


def test_tier_answer_refuses_text_the_way_the_surface_refuses_a_string(
    loaded: JsRuntime,
):
    """The surface raises for a string balance. The module refuses rather than
    guessing by coercing the text to a number."""
    with pytest.raises(TypeError):
        surface.tier_for_target_balance("100")
    tier, refusal = loaded.tier_answer("100")
    assert tier == ""
    assert refusal != ""


def test_tier_answer_refuses_null_and_a_list(loaded: JsRuntime):
    refused: tuple[Any, ...] = (None, [1, 2], {})
    for value in refused:
        loaded.bind_json("BALANCE", value)
        tier, refusal = loaded.json(
            "acervatorVisualizerThemes.tierAnswer(JSON.parse(BALANCE))"
        )
        assert tier == ""
        assert refusal != ""


def test_tier_answer_refuses_before_the_module_loads(js: JsRuntime):
    tier, refusal = js.tier_answer(50)
    assert tier == ""
    assert refusal != ""


# -- 5. defect 4: no non-finite number reaches an outgoing bridge call --


BRIDGE_STUB = (
    "window.CALLS = [];"
    "window.acervator = { call: function (method, params) {"
    "  window.CALLS.push(JSON.stringify(params));"
    "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
)


def test_a_non_finite_balance_never_reaches_the_outgoing_call(js: JsRuntime):
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run(
        "acervatorLoadVisualizerThemes(undefined, undefined, NaN);"
        "acervatorVisualizerThemes.forget();"
        "acervatorLoadVisualizerThemes(undefined, undefined, Infinity);"
    )
    drain_events()
    calls = js.json("window.CALLS")
    for call in calls:
        assert "NaN" not in call
        assert "Infinity" not in call
        assert "target_balance" not in call


def test_a_finite_balance_does_reach_the_outgoing_call(js: JsRuntime):
    """The control. Without the guard the check above could pass by omitting
    every balance, finite or not."""
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadVisualizerThemes(undefined, undefined, 250);")
    drain_events()
    assert js.json("window.CALLS") == ['{"target_balance":250}']


# -- 6. defect 5: a refusal must not look like an answer -----------------


def test_has_theme_is_false_for_an_unknown_name(loaded: JsRuntime):
    loaded.bind_json("N", "no_such_theme")
    assert loaded.json("acervatorVisualizerThemes.hasTheme(JSON.parse(N))") is False
    assert loaded.theme_values("no_such_theme") == {}


def test_has_theme_is_true_for_a_theme_whose_values_are_all_blank(js: JsRuntime):
    """The control for the check above: a real-but-blank theme must read
    differently from no theme at all."""
    payload = bridge_payload()
    payload["themes"]["blank"] = {f: "" for f in surface.THEME_FIELD_NAMES}
    js.push(payload)
    js.bind_json("N", "blank")
    assert js.json("acervatorVisualizerThemes.hasTheme(JSON.parse(N))") is True
    assert js.theme_values("blank") == {f: "" for f in surface.THEME_FIELD_NAMES}


def test_has_tier_tells_the_same_two_cases_apart(js: JsRuntime):
    payload = bridge_payload()
    payload["tier_palettes"]["blank"] = {f: "" for f in surface.TIER_FIELD_NAMES}
    js.push(payload)
    js.bind_json("MISSING", "no_such_tier")
    js.bind_json("BLANK", "blank")
    assert js.json("acervatorVisualizerThemes.hasTier(JSON.parse(MISSING))") is False
    assert js.json("acervatorVisualizerThemes.hasTier(JSON.parse(BLANK))") is True
    assert js.tier_values("no_such_tier") == {}
    assert js.tier_values("blank") == {f: "" for f in surface.TIER_FIELD_NAMES}


@pytest.mark.parametrize("value", [None, 0, -1, 9.5, True, [], ["nebula"], {}, ()])
def test_requested_name_refuses_anything_that_is_not_text(js: JsRuntime, value):
    assert surface.requested_name(value) == ""
    js.bind_json("V", value)
    assert js.json("acervatorVisualizerThemes.requestedName(JSON.parse(V))") == ""


def test_requested_name_answers_real_text(js: JsRuntime):
    for name in (FIRST_THEME, "", "not_a_real_theme", "Δ→⚡"):
        js.bind_json("V", name)
        assert (
            js.json("acervatorVisualizerThemes.requestedName(JSON.parse(V))")
            == surface.requested_name(name)
            == name
        )


def test_unknown_theme_and_unknown_tier_are_relayed_from_the_surface(js: JsRuntime):
    js.push(bridge_payload(name="no_such_theme", tier="no_such_tier"))
    assert js.json("acervatorVisualizerThemes.unknownTheme()") == ["no_such_theme"]
    assert js.json("acervatorVisualizerThemes.unknownTier()") == ["no_such_tier"]


def test_a_known_request_carries_no_unknown_name(js: JsRuntime):
    """The control. Asking for a real theme must not be reported as unknown."""
    js.push(bridge_payload(name=FIRST_THEME, tier=FIRST_TIER))
    assert js.json("acervatorVisualizerThemes.unknownTheme()") == []
    assert js.json("acervatorVisualizerThemes.unknownTier()") == []


def test_the_requested_theme_and_tier_and_the_asked_answer_are_relayed(js: JsRuntime):
    payload = bridge_payload(name=SECOND_THEME, tier=SECOND_TIER, target_balance=50)
    js.push(payload)
    assert js.json("acervatorVisualizerThemes.requestedTheme()") == SECOND_THEME
    assert js.json("acervatorVisualizerThemes.requestedTier()") == SECOND_TIER
    assert js.json("acervatorVisualizerThemes.theme()") == surface.THEMES[SECOND_THEME]
    assert (
        js.json("acervatorVisualizerThemes.tierPalette()")
        == surface.TIER_PALETTES[SECOND_TIER]
    )
    assert js.json(
        "acervatorVisualizerThemes.tier()"
    ) == surface.tier_for_target_balance(50)
    assert js.json("acervatorVisualizerThemes.targetBalanceText()") == repr(50)


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(js: JsRuntime):
    for wrong in ("a string", 7, None, ["a", "list"]):
        report = js.push(wrong)
        assert report == {"loaded": False, "fault": "not-an-object"}
        assert js.json("acervatorVisualizerThemes.isLoaded()") is False
        assert js.json("acervatorVisualizerThemes.themeNames()") == []


def test_a_real_payload_reports_loaded(js: JsRuntime):
    """The control for the check above."""
    report = js.push(bridge_payload())
    assert report == {"loaded": True, "fault": None}
    assert js.json("acervatorVisualizerThemes.isLoaded()") is True


# -- 7. the module reports only what it was given ------------------------


def test_the_module_reports_only_what_it_was_given(js: JsRuntime):
    invented = {f: "given-" + f for f in surface.THEME_FIELD_NAMES}
    js.push(
        {
            "theme_names": [FIRST_THEME],
            "themes": {FIRST_THEME: invented},
            "tier_names": [],
            "tier_palettes": {},
        }
    )
    actual = js.theme_values(FIRST_THEME)
    assert actual == invented
    assert not set(actual.values()) & surface_values()


# -- 8. the bridge ask ----------------------------------------------------


def test_the_module_asks_the_backend_for_the_surface_method(js: JsRuntime):
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadVisualizerThemes();")
    drain_events()
    assert js.json("window.CALLS") == ["{}"]
    assert js.json("acervatorVisualizerThemes.isLoaded()") is True


def test_the_module_asks_for_one_theme_and_tier_by_name(js: JsRuntime):
    js.bind_json("PAYLOAD", bridge_payload(name=SECOND_THEME, tier=SECOND_TIER))
    js.run(BRIDGE_STUB)
    js.bind_json("NAME", SECOND_THEME)
    js.bind_json("TIER", SECOND_TIER)
    js.run("acervatorLoadVisualizerThemes(JSON.parse(NAME), JSON.parse(TIER));")
    drain_events()
    sent = json.loads(js.json("window.CALLS")[0])
    assert sent == {"name": SECOND_THEME, "tier": SECOND_TIER}


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime):
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run(
        "acervatorLoadVisualizerThemes(); acervatorLoadVisualizerThemes();"
        "acervatorLoadVisualizerThemes();"
    )
    drain_events()
    assert len(js.json("window.CALLS")) == 1


def test_the_ask_counter_reports_a_second_round_trip(js: JsRuntime):
    """The control. A counter that never incremented would report one call
    however many were made."""
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadVisualizerThemes();")
    drain_events()
    js.run("acervatorVisualizerThemes.forget(); acervatorLoadVisualizerThemes();")
    drain_events()
    assert len(js.json("window.CALLS")) == 2


def test_the_module_reports_a_missing_bridge_rather_than_raising(js: JsRuntime):
    js.run("acervatorLoadVisualizerThemes();")
    drain_events()
    assert js.json("acervatorVisualizerThemes.isLoaded()") is False
    assert (
        js.json("acervatorVisualizerThemes.loadError()")
        == "the preload bridge is not present"
    )


def test_a_refused_ask_is_not_remembered(js: JsRuntime):
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(
        "window.TRIES = 0;"
        "window.acervator = { call: function () {"
        "  window.TRIES += 1;"
        "  if (window.TRIES === 1) {"
        "    return Promise.reject(new Error('the Python backend is not running')); }"
        "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
        "acervatorLoadVisualizerThemes();"
    )
    drain_events()
    assert js.json("acervatorVisualizerThemes.isLoaded()") is False
    js.run("acervatorLoadVisualizerThemes();")
    drain_events()
    assert js.json("window.TRIES") == 2
    assert js.json("acervatorVisualizerThemes.isLoaded()") is True


# -- 9. everything the surface publishes but paints nothing --------------


def test_actions_timers_and_bus_topics_are_always_empty(loaded: JsRuntime):
    assert loaded.json("acervatorVisualizerThemes.actions()") == {}
    assert loaded.json("acervatorVisualizerThemes.timers()") == {}
    assert loaded.json("acervatorVisualizerThemes.timerDelaysMs()") == []
    assert loaded.json("acervatorVisualizerThemes.busTopics()") == []
    assert loaded.json("acervatorVisualizerThemes.skin()") == {}
    assert surface.ACTIONS == {}
    assert surface.TIMERS == {}
    assert surface.BUS_TOPICS == ()


# -- 10. module registration and load order ------------------------------


def test_the_module_is_registered_for_the_renderer_to_load():
    assert MODULE_PATH.name in load_order()


def test_the_module_runs_after_the_loader_that_injects_it():
    order = load_order()
    assert runs_after(order, MODULE_PATH.name, "module_loader.js")


def test_runs_after_reports_false_for_a_dependency_that_runs_later():
    """The control. A hand-built order where the dependency comes after
    the module must not read as satisfied."""
    order = [MODULE_PATH.name, "module_loader.js"]
    assert runs_after(order, MODULE_PATH.name, "module_loader.js") is False


def test_runs_after_reports_false_for_a_name_absent_from_the_order():
    assert (
        runs_after(["module_loader.js"], MODULE_PATH.name, "module_loader.js") is False
    )


# -- the module under the page's own policy -------------------------------


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtCore import QEventLoop, QTimer, QUrl
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        loop = QEventLoop()
        box: dict = {}

        def _loaded(ok: bool) -> None:
            box.setdefault("ok", ok)
            loop.quit()

        self._view.loadFinished.connect(_loaded)
        self._view.load(QUrl.fromLocalFile(str(INDEX_HTML)))
        QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        assert box.get("ok") is True, f"{INDEX_HTML.name} did not load: {box}"

    def js(self, script: str) -> Any:
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        box: dict = {}

        def _answered(value: Any) -> None:
            box.setdefault("v", value)
            loop.quit()

        self._view.page().runJavaScript(script, _answered)
        QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        assert "v" in box, "the browser never answered: " + script[:80]
        return box["v"]

    def settle(self, milliseconds: int) -> None:
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        QTimer.singleShot(milliseconds, loop.quit)
        loop.exec()

    def close(self) -> None:
        self._view.deleteLater()


@pytest.fixture()
def browser(qapp):
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    page = Browser()
    yield page
    page.close()


WATCH_VIOLATIONS = (
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
)


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorVisualizerThemes") == "object"
    assert browser.js("typeof window.acervatorSetVisualizerThemes") == "function"
    assert browser.js("typeof window.acervatorLoadVisualizerThemes") == "function"


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(bridge_payload())) + ";")
    browser.js(
        "acervatorSetVisualizerThemes(JSON.parse(window.PAYLOAD));"
        "acervatorVisualizerThemes.themeColours(" + json.dumps(FIRST_THEME) + ");"
        "acervatorVisualizerThemes.tierAnswer(500);"
    )
    browser.settle(500)
    assert json.loads(browser.js("JSON.stringify(window.VIOLATIONS)")) == []


def test_the_policy_refuses_a_network_call_from_the_loaded_page(browser: Browser):
    """The control for the check above."""
    browser.js(
        WATCH_VIOLATIONS + "window.PROBE = 'pending';"
        "fetch('https://example.invalid/x')"
        "  .then(function () { window.PROBE = 'allowed'; })"
        "  .catch(function (e) { window.PROBE = 'refused: ' + e.name; });"
    )
    browser.settle(1500)
    assert browser.js("window.PROBE") == "refused: TypeError"
    violations = json.loads(browser.js("JSON.stringify(window.VIOLATIONS)"))
    assert any(v.startswith("connect-src") for v in violations), violations

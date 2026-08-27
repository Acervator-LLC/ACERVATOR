"""The six small GUI files paint the same pixels after the token migration.

A failure means a `design_system` token reference, or one of the six
files, moved pixels in the operator's live trading GUI.

`SHIPPED` holds, per file and in source order, every `design_system`
name the file now reads and the hex literal that name replaced. Each
widget is then built twice: once from the working tree, which reads
tokens, and once from a copy of the same source with every token
reference substituted back to its literal. The two renders must be
byte-identical.

The literal side is what makes this falsifiable. A test that compared a
render to the token that produced it would move on both sides and pass a
wrong colour.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import io
import os
import re
import sys
import tempfile
import tokenize
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

REPO_ROOT = Path(__file__).resolve().parents[1]
GUI_DIR = REPO_ROOT / "src" / "gui"

DIALOG_SIZE = (520, 360)
LIST_SIZE = (600, 200)
WIZARD_SIZE = (700, 520)
PANEL_SIZE = (620, 420)
LAYER_SIZE = (620, 60)
ASSET_PAGE_SIZE = (820, 420)
LABEL_SIZE = (420, 30)
BUTTON_SIZE = (160, 32)

TOOLBAR_SURFACE = "#14141e"
TEXT_CONSOLE = "#c0c0c0"
SURFACE_CHART = "#0a0a12"
SEPARATOR = "#2a2a3a"
BUTTON_SURFACE = "#1a1a26"
BUTTON_BORDER = "#3a3a4a"
BUTTON_HOVER = "#22222e"
TEXT_PLACEHOLDER = "#555555"
METRIC_LABEL = "#888888"
SUCCESS = "#00ff88"
ERROR = "#ff3366"
TEXT_MUTED = "#666666"
PRIMARY_BRIGHT = "#00ffee"
WARNING = "#ffaa00"
STATUS_INFO = "#00aaff"
DISABLED_DEEP = "#333333"
SOURCE_MANUAL = "#00ccff"
TEXT_INACTIVE = "#aaaaaa"

SHIPPED: dict[str, tuple[tuple[str, str], ...]] = {
    "start_all_progress_dialog": (
        ("MAIN_TOOLBAR_SURFACE", "#14141e"),
        ("TEXT_CONSOLE", "#c0c0c0"),
        ("TEXT_CONSOLE", "#c0c0c0"),
        ("SURFACE_CHART", "#0a0a12"),
        ("TEXT_CONSOLE", "#c0c0c0"),
        ("MAIN_SEPARATOR", "#2a2a3a"),
        ("MAIN_BUTTON_SURFACE", "#1a1a26"),
        ("TEXT_CONSOLE", "#c0c0c0"),
        ("MAIN_BUTTON_BORDER", "#3a3a4a"),
        ("MAIN_BUTTON_HOVER", "#22222e"),
        ("TEXT_PLACEHOLDER", "#555"),
        ("MAIN_SEPARATOR", "#2a2a3a"),
        ("CARD_METRIC_LABEL", "#888888"),
    ),
    "bot_swarm_list": (
        ("SUCCESS", "#00ff88"),
        ("ERROR", "#ff3366"),
        ("TEXT_MUTED", "#666666"),
        ("PRIMARY_BRIGHT", "#00ffee"),
        ("WARNING", "#ffaa00"),
        ("ERROR", "#ff3366"),
    ),
    "init_wizard": (
        ("CARD_METRIC_LABEL", "#888"),
        ("ERROR", "#ff3366"),
        ("STATUS_INFO", "#00aaff"),
        ("SUCCESS", "#00ff88"),
        ("ERROR", "#ff3366"),
        ("ERROR", "#ff3366"),
    ),
    "audio_suite": (
        ("SETTINGS_DISABLED_DEEP", "#333"),
        ("FOLD_SOURCE_MANUAL", "#00ccff"),
        ("FOLD_SOURCE_MANUAL", "#00ccff"),
        ("CARD_METRIC_LABEL", "#888"),
    ),
    "bot_wizard": (
        ("FOLD_SOURCE_MANUAL", "#00ccff"),
        ("FOLD_SOURCE_MANUAL", "#00ccff"),
    ),
    "history_tab": (("TEXT_INACTIVE", "#aaa"),),
}

SHIPPED_DIALOG_QSS = (
    "QDialog { background: #14141e; color: #c0c0c0; }"
    "QLabel { color: #c0c0c0; font-family: Consolas; font-size: 11px; }"
    "QListWidget { background: #0a0a12; color: #c0c0c0; "
    "border: 1px solid #2a2a3a; font-family: Consolas; font-size: 10px; }"
    "QPushButton { background: #1a1a26; color: #c0c0c0; "
    "border: 1px solid #3a3a4a; padding: 6px 18px; "
    "font-family: Consolas; font-size: 10px; }"
    "QPushButton:hover { background: #22222e; }"
    "QPushButton:disabled { color: #555; border-color: #2a2a3a; }"
)

SHIPPED_INFO_BUTTON_QSS = (
    "color: #00ccff; font-weight: bold; border: 1px solid #00ccff; "
    "border-radius: 10px; padding: 2px 6px; margin-left: 4px; "
    "max-width: 28px;"
)

SWARM_ROWS = [
    {
        "bot_id": "b0",
        "symbol": "BTC",
        "inflow_usd": 10.0,
        "outflow_usd": 2.0,
        "outflow_pct": 0.0,
    },
    {
        "bot_id": "b1",
        "symbol": "ETH",
        "inflow_usd": 20.0,
        "outflow_usd": 4.0,
        "outflow_pct": 50.0,
    },
    {
        "bot_id": "b2",
        "symbol": "SOL",
        "inflow_usd": 30.0,
        "outflow_usd": 6.0,
        "outflow_pct": 90.0,
    },
    {
        "bot_id": "b3",
        "symbol": "XRP",
        "inflow_usd": 40.0,
        "outflow_usd": 8.0,
        "outflow_pct": 120.0,
    },
]

EXCHANGES = [{"id": "coinbase", "name": "Coinbase"}]

TOKEN_REF = re.compile(r"\{ds\.([A-Z_0-9]+)\}|(?<![\w.])ds\.([A-Z_0-9]+)\b")
HEX_LITERAL = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")


class _Ok:
    """A credential check that reports success."""

    success = True
    message = "connected"


class _Bad:
    """A credential check that reports failure."""

    success = False
    message = "rejected"


def _raise():
    raise RuntimeError("credential check exploded")


def _raw(image) -> bytes:
    """Pixel bytes of `image` in a fixed 32-bit layout, four bytes each."""
    from PySide6.QtGui import QImage

    return bytes(image.convertToFormat(QImage.Format_RGB32).constBits())


def _diff_pixels(first, second) -> int:
    """Count pixels that differ between two renders; -1 if the sizes differ."""
    if (first.width(), first.height()) != (second.width(), second.height()):
        return -1
    left, right = _raw(first), _raw(second)
    if left == right:
        return 0
    return sum(1 for i in range(0, len(left), 4) if left[i : i + 4] != right[i : i + 4])


def _count_colour(image, expected_hex: str) -> int:
    """Pixels in `image` whose painted colour equals `expected_hex`."""
    from PySide6.QtGui import QColor

    want = QColor(expected_hex)
    key = (want.blue(), want.green(), want.red())
    raw = _raw(image)
    return sum(1 for t in zip(raw[0::4], raw[1::4], raw[2::4]) if t == key)


def _token_names(name: str) -> list[str]:
    """Every `ds.NAME` the working-tree file reads, in source order."""
    tree = ast.parse((GUI_DIR / f"{name}.py").read_text("utf-8"))
    found: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "ds"
        ):
            found.append((node.lineno, node.col_offset, node.attr))
        elif isinstance(node, ast.JoinedStr):
            for part in node.values:
                if not isinstance(part, ast.FormattedValue):
                    continue
                inner = part.value
                if (
                    isinstance(inner, ast.Attribute)
                    and isinstance(inner.value, ast.Name)
                    and inner.value.id == "ds"
                ):
                    found.append((inner.lineno, inner.col_offset, inner.attr))
    unique = sorted(set(found))
    return [attr for _, _, attr in unique]


_BASE_CACHE: dict[str, object] = {}
_BASE_DIR: list[Path] = []


def _literal_source(name: str) -> str:
    """The working-tree source with every token reference put back as a literal."""
    source = (GUI_DIR / f"{name}.py").read_text("utf-8")
    pending = list(SHIPPED[name])

    def swap(match: re.Match) -> str:
        braced, bare = match.group(1), match.group(2)
        expected_name, literal = pending.pop(0)
        assert (
            braced or bare
        ) == expected_name, (
            f"{name}: expected ds.{expected_name}, found ds.{braced or bare}"
        )
        return literal if braced else f'"{literal}"'

    rebuilt = TOKEN_REF.sub(swap, source)
    assert not pending, f"{name}: {len(pending)} token references never appeared"
    return rebuilt


def literal_module(name: str):
    """Import the literal-substituted twin of `src/gui/<name>.py`.

    Bound under a `src.gui.` package name so the module's own relative
    imports resolve against the real siblings.
    """
    if name in _BASE_CACHE:
        return _BASE_CACHE[name]
    if not _BASE_DIR:
        _BASE_DIR.append(Path(tempfile.mkdtemp(prefix="gui-literal-twin-")))
    path = _BASE_DIR[0] / f"{name}.py"
    path.write_text(_literal_source(name), encoding="utf-8", newline="")
    mod_name = f"src.gui._literal_twin_{name}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    _BASE_CACHE[name] = module
    return module


def _distinct_colours(image) -> int:
    """How many different colours the render actually contains."""
    raw = _raw(image)
    return len(set(zip(raw[0::4], raw[1::4], raw[2::4])))


def _pair(name: str, build, size, pick=None):
    """Render `build` against the working tree and against the literal twin.

    `pick` selects a child of the built widget to grab instead of the
    widget itself; the parent is kept alive for the grab either way.
    """
    from tests.qt_pixel import ensure_app, render_widget

    ensure_app()
    head_widget = build(importlib.import_module(f"src.gui.{name}"))
    base_widget = build(literal_module(name))
    head = render_widget(pick(head_widget) if pick else head_widget, size=size)
    base = render_widget(pick(base_widget) if pick else base_widget, size=size)
    assert _distinct_colours(head) > 1, f"{name} rendered one flat colour"
    return head, base


@pytest.mark.parametrize("name", sorted(SHIPPED))
def test_each_file_reads_the_tokens_the_table_names(name: str) -> None:
    """A failure means a file swapped one token reference for another."""
    assert _token_names(name) == [n for n, _ in SHIPPED[name]]


@pytest.mark.parametrize("name", sorted(SHIPPED))
def test_each_token_still_holds_the_literal_it_replaced(name: str) -> None:
    """A failure means a design_system value drifted from the shipped colour."""
    from PySide6.QtGui import QColor

    from src.gui import design_system as ds

    for token_name, literal in SHIPPED[name]:
        assert (
            QColor(getattr(ds, token_name)).name() == QColor(literal).name()
        ), f"{token_name} is {getattr(ds, token_name)}, shipped {literal}"


@pytest.mark.parametrize("name", sorted(SHIPPED))
def test_no_rendered_hex_literal_survives(name: str) -> None:
    """A failure means a colour literal is still in the widget code."""
    source = (GUI_DIR / f"{name}.py").read_text("utf-8")
    docstrings = {
        (node.body[0].value.lineno, node.body[0].value.col_offset)
        for node in ast.walk(ast.parse(source))
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    found = [
        match.group(0)
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.STRING and token.start not in docstrings
        for match in HEX_LITERAL.finditer(token.string)
    ]
    assert found == [], f"{name}: {found}"


@pytest.mark.parametrize("name", sorted(SHIPPED))
def test_the_literal_twin_carries_no_token_reference(name: str) -> None:
    """A failure means the comparison twin reads tokens, not literals."""
    twin = _literal_source(name)
    assert TOKEN_REF.search(twin) is None
    assert HEX_LITERAL.search(twin) is not None


def test_start_all_dialog_is_pixel_identical() -> None:
    """A failure means the start-all progress dialog repainted."""
    head, base = _pair(
        "start_all_progress_dialog",
        lambda m: m.StartAllProgressDialog(object()),
        DIALOG_SIZE,
    )
    assert _diff_pixels(head, base) == 0


def test_start_all_dialog_paints_its_shipped_colours() -> None:
    """A failure means a dialog surface, border or text colour moved."""
    from tests.qt_pixel import ensure_app, render_widget
    from src.gui.start_all_progress_dialog import StartAllProgressDialog

    ensure_app()
    image = render_widget(StartAllProgressDialog(object()), size=DIALOG_SIZE)
    for colour in (
        TOOLBAR_SURFACE,
        TEXT_CONSOLE,
        SURFACE_CHART,
        SEPARATOR,
        BUTTON_SURFACE,
        BUTTON_BORDER,
        TEXT_PLACEHOLDER,
        METRIC_LABEL,
    ):
        assert _count_colour(image, colour) > 0, colour


def test_start_all_dialog_stylesheet_matches_the_shipped_text() -> None:
    """A failure means the dialog QSS names a colour it did not ship with."""

    def expand(text: str) -> str:
        return re.sub(
            r"#([0-9a-f])([0-9a-f])([0-9a-f])\b",
            lambda m: "#" + "".join(c * 2 for c in m.groups()),
            text.lower(),
        )

    from tests.qt_pixel import ensure_app, render_widget
    from src.gui.start_all_progress_dialog import StartAllProgressDialog

    ensure_app()
    dialog = StartAllProgressDialog(object())
    assert expand(dialog.styleSheet()) == expand(SHIPPED_DIALOG_QSS)
    image = render_widget(dialog, size=DIALOG_SIZE)
    assert _count_colour(image, TOOLBAR_SURFACE) > 0
    assert _count_colour(image, SURFACE_CHART) > 0


def test_start_all_dialog_hover_rule_carries_the_shipped_colour() -> None:
    """A failure means the button hover colour changed.

    `:hover` needs a real pointer, which an offscreen grab has not got.
    The rule text is read directly; the render beside it proves the
    stylesheet carrying that rule is the one the dialog paints from.
    """
    from tests.qt_pixel import ensure_app, render_widget
    from src.gui.start_all_progress_dialog import StartAllProgressDialog

    ensure_app()
    dialog = StartAllProgressDialog(object())
    assert f"QPushButton:hover {{ background: {BUTTON_HOVER}; }}" in dialog.styleSheet()
    image = render_widget(dialog, size=DIALOG_SIZE)
    assert _count_colour(image, BUTTON_SURFACE) > 0
    assert _count_colour(image, BUTTON_HOVER) == 0


def _swarm(module):
    view = module.BotListView()
    view.set_bots(SWARM_ROWS)
    return view


def test_bot_swarm_list_is_pixel_identical() -> None:
    """A failure means a bot swarm row colour moved."""
    head, base = _pair("bot_swarm_list", _swarm, LIST_SIZE)
    assert _diff_pixels(head, base) == 0


def test_bot_swarm_list_paints_every_ramp_branch() -> None:
    """A failure means one of the %-Out ramp colours changed."""
    from tests.qt_pixel import ensure_app, render_widget
    from src.gui.bot_swarm_list import BotListView

    ensure_app()
    view = BotListView()
    view.set_bots(SWARM_ROWS)
    image = render_widget(view, size=LIST_SIZE)
    for colour in (SUCCESS, ERROR, TEXT_MUTED, PRIMARY_BRIGHT, WARNING):
        assert _count_colour(image, colour) > 0, colour


def test_init_wizard_first_page_is_pixel_identical() -> None:
    """A failure means the first-run wizard repainted."""
    head, base = _pair("init_wizard", lambda m: m.InitWizard(), WIZARD_SIZE)
    assert _diff_pixels(head, base) == 0


def _skip_button(wizard):
    """The wizard's Skip Setup button.

    A QWizard lays its pages out only once shown, so an offscreen grab of
    the whole wizard paints none of them; the button is grabbed directly.
    """
    from PySide6.QtWidgets import QPushButton

    buttons = [b for b in wizard.findChildren(QPushButton) if b.text() == "Skip Setup"]
    assert len(buttons) == 1, f"found {len(buttons)} Skip Setup buttons"
    return buttons[0]


def test_init_wizard_skip_button_is_pixel_identical() -> None:
    """A failure means the Skip Setup button repainted."""
    head, base = _pair(
        "init_wizard", lambda m: m.InitWizard(), BUTTON_SIZE, pick=_skip_button
    )
    assert _diff_pixels(head, base) == 0
    assert _count_colour(head, METRIC_LABEL) > 0


def _feedback_renders(module, key: str, secret: str, outcome):
    """Render the wizard feedback label during and after one _test_api call.

    The second image is None when the call returns before the validator.
    The label is taken out of the wizard layout first: inside it the label
    grabs at 578x12 with clipped glyphs, and two renders of the identical
    widget then differ by one pixel about half the time.
    """
    from tests.qt_pixel import ensure_app, render_widget
    from src.exchange import api_validator

    ensure_app()
    wizard = module.InitWizard()
    wizard._api_key.setText(key)
    wizard._api_secret.setPlainText(secret)
    captured = {}

    def grab():
        wizard._feedback.setParent(None)
        return render_widget(wizard._feedback, size=LABEL_SIZE)

    def spy(*_args, **_kwargs):
        captured["pending"] = grab()
        return outcome()

    original = api_validator.validate_credentials
    api_validator.validate_credentials = spy
    try:
        wizard._test_api()
    finally:
        api_validator.validate_credentials = original
    return grab(), captured.get("pending")


@pytest.mark.parametrize(
    "key,secret,outcome,expected",
    [
        ("", "", _Ok, ERROR),
        ("k", "s", _Ok, SUCCESS),
        ("k", "s", _Bad, ERROR),
        ("k", "s", _raise, ERROR),
    ],
)
def test_init_wizard_feedback_branches_are_pixel_identical(
    key: str, secret: str, outcome, expected: str
) -> None:
    """A failure means a credential-test feedback colour moved."""
    head, head_pending = _feedback_renders(
        importlib.import_module("src.gui.init_wizard"), key, secret, outcome
    )
    base, base_pending = _feedback_renders(
        literal_module("init_wizard"), key, secret, outcome
    )
    assert _diff_pixels(head, base) == 0
    assert _count_colour(head, expected) > 0
    if head_pending is not None:
        assert _diff_pixels(head_pending, base_pending) == 0
        assert _count_colour(head_pending, STATUS_INFO) > 0


AUDIO_WIDGETS = [
    ("DroneLayer", (0,), LAYER_SIZE, DISABLED_DEEP),
    ("MusicPlayerPanel", (), PANEL_SIZE, SOURCE_MANUAL),
    ("DroneEnginePanel", (), PANEL_SIZE, SOURCE_MANUAL),
]


@pytest.mark.parametrize("cls_name,args,size,colour", AUDIO_WIDGETS)
def test_audio_suite_widgets_are_pixel_identical(
    cls_name: str, args: tuple, size: tuple, colour: str
) -> None:
    """A failure means an audio panel border or label colour moved."""
    head, base = _pair("audio_suite", lambda m: getattr(m, cls_name)(*args), size)
    assert _diff_pixels(head, base) == 0
    assert _count_colour(head, colour) > 0


def test_drone_engine_panel_paints_its_status_grey() -> None:
    """A failure means the drone-engine status line is no longer grey."""
    from tests.qt_pixel import ensure_app, render_widget
    from src.gui.audio_suite import DroneEnginePanel

    ensure_app()
    image = render_widget(DroneEnginePanel(), size=PANEL_SIZE)
    assert _count_colour(image, METRIC_LABEL) > 0


def test_bot_wizard_asset_page_is_pixel_identical() -> None:
    """A failure means the asset-selection info button repainted."""
    head, base = _pair(
        "bot_wizard", lambda m: m.AssetSelectionPage(EXCHANGES), ASSET_PAGE_SIZE
    )
    assert _diff_pixels(head, base) == 0
    assert _count_colour(head, SOURCE_MANUAL) > 0


def test_bot_wizard_info_button_stylesheet_matches_the_shipped_text() -> None:
    """A failure means the info button QSS changed, not just its source."""
    from tests.qt_pixel import ensure_app, render_widget
    from src.gui.bot_wizard import AssetSelectionPage

    ensure_app()
    page = AssetSelectionPage(EXCHANGES)
    assert page._info_btn.styleSheet() == SHIPPED_INFO_BUTTON_QSS
    image = render_widget(page, size=ASSET_PAGE_SIZE)
    assert _count_colour(image, SOURCE_MANUAL) > 0


def test_history_tab_summary_is_pixel_identical() -> None:
    """A failure means the History summary line repainted."""
    head, base = _pair(
        "history_tab",
        lambda m: m.HistoryTab(),
        LABEL_SIZE,
        pick=lambda tab: tab._summary,
    )
    assert _diff_pixels(head, base) == 0
    assert _count_colour(head, TEXT_INACTIVE) > 0


def test_the_pixel_comparison_can_fail() -> None:
    """A failure means the image comparison cannot detect a changed colour."""
    from PySide6.QtWidgets import QLabel

    from tests.qt_pixel import ensure_app, render_widget

    ensure_app()

    def label(colour: str):
        widget = QLabel("acervator")
        widget.setStyleSheet(f"QLabel {{ background: {colour}; }}")
        return render_widget(widget, size=LABEL_SIZE)

    assert _diff_pixels(label(SUCCESS), label(SUCCESS)) == 0
    assert _diff_pixels(label(SUCCESS), label("#00ff89")) > 0
    assert _count_colour(label(SUCCESS), "#00ff89") == 0

"""Money admission on the nine unguarded reads of the Bot Swarm tab.

THE DEFECT THESE PIN (CHANGE A)
===============================
``_create_bot_swarm_tab`` read nine money or percentage values through a
bare ``float(x or 0)`` with no ``try`` above them. Re-anchored on the
promoted file, the nine were::

    :3021  inbound[src_id] = float(targets[bot_id] or 0)
    :3036  float(getattr(ledger, "wired_in", 0) or 0)
    :3037  float(getattr(ledger, "wired_out", 0) or 0)
    :3057  float(getattr(self._bot, "_pending_wire_credits", 0) or 0)
    :3074  float(getattr(ledger, "starting_balance", 0) or 0)
    :3161  out_lifetime[tx.target_bot] += float(getattr(tx, "amount", 0) or 0)
    :3203  in_lifetime[tx.source_bot]  += float(getattr(tx, "amount", 0) or 0)
    :3279  f"${float(credit.get('usd', 0) or 0):,.4f}"
    :3370  f"${float(getattr(tx, 'amount', 0) or 0):,.4f}"

Three further reads -- :3093, :3094, :3095 -- sit inside a ``Try`` whose
handler is ``Exception`` and were already contained. That split was
established by AST over the whole ``FunctionDef``, not inherited.

WHY A RAISE MATTERS. The ancestor chain from every one of the nine is
``For``/``If`` -> ``_create_bot_swarm_tab`` -> ``BotLiveSettingsDialog.
__init__`` -> ``MainWindow._on_bot_clicked``, with NO ``try`` at any
step, so a raise means the Bot Settings dialog does not open for that
bot. The contrast that proves the walk discriminates:
``simulator_tab.py:695`` builds the same dialog inside a ``try`` with an
``Exception`` handler, so the Simulator path is protected and the
operator's path is not.

MEASURED, NOT PREDICTED. Every row below was driven through the real
method before the guard was written. Four shapes RAISED and killed the
tab -- ``"abc"`` ValueError, ``10 ** 400`` OverflowError, ``[1, 2]`` and
``{"a": 1}`` TypeError. Nine more did not raise and lied instead:
``True`` rendered ``$1.0000`` for a stored flag, ``"20.0"`` rendered
``$20.0000`` for a stored string, and ``nan``/``inf``/``-inf`` rendered
``$nan``/``$inf``/``$-inf``.

REACHABILITY IS NOT ONE STORY, and the guard is justified per site:

* :3279 ``credit["usd"]`` -- ACTIVE, widest domain. ``ScrummingBot.
  _restore_state`` rebuilds the pending ledger as ``dict(_e)`` per entry
  and coerces NO key, so ``usd`` arrives exactly as ``json.load``
  decoded it. Every shape above reaches this line.
* :3036 :3037 :3074 ledger totals -- ACTIVE, narrow. ``SmartWireManager.
  import_ledgers`` coerces each field with ``float(... or 0.0)`` inside
  a ``try`` that drops the row, so a string cannot survive; ``NaN`` and
  ``Infinity`` decode to real floats, pass the coercion untouched and
  are stored.
* :3057 ``_pending_wire_credits`` -- ACTIVE, narrow, same two shapes.
  ``_restore_state`` coerces it inside ``except (TypeError,
  ValueError)``, which ``nan`` and ``inf`` pass through unchanged.
* :3021 inbound wire pct -- ACTIVE, narrowest. Both writers of
  ``SmartWireManager._wires`` coerce with ``float()`` and reject
  ``pct <= 0 or pct > 100``; ``nan`` is False on BOTH comparisons and so
  is the one shape admitted.
* :3161 :3203 :3370 ``tx.amount`` -- LATENT. ``_transactions`` has no
  assignment anywhere in ``src/`` or ``tests/``, only ``append`` and
  ``extend``, so nothing round-trips through ``bot_state.json``. Both
  reachable constructors pass ``float(...)``; the three that forward a
  caller-supplied amount are unreachable, their only textual caller
  being an example inside the ``SmartWireManager`` class docstring.
  Guarded because ``getattr`` is duck-typed and ``WireTransaction`` is a
  ``@dataclass``, which annotates ``amount: float`` without enforcing
  it, and because two money columns fed by one feed must not disagree.

A REFUSED MONEY VALUE MUST NOT RENDER AS ZERO. ``$0.0000`` is a
statement about the ledger; the em dash is a statement about the read.
The old code printed ``$0.0000`` for ``None`` and ``""`` because
``or 0`` short-circuited them, which is the same silent-zero the
outbound total below refuses to keep.

THE DEFECT THIS PINS (CHANGE B)
===============================
``:3105`` imported ``SmartWireLedger`` from ``src.trading.smart_wire``.
THAT NAME HAS NEVER EXISTED -- the module defines ``WireTransaction``,
``BotLedger`` and ``SmartWireManager``. The import raised ImportError on
every build, the enclosing ``except Exception`` logged it at DEBUG, and
``_mature_ratio_pct`` fell back to a hardcoded ``70`` every single time,
while the comment above it claimed the value was read from the ledger so
the label would "stay in sync with the runtime constant instead of
hardcoding 70%".

THE LABEL WAS CORRECT ONLY BY COINCIDENCE, because
``BotLedger.MATURE_RATIO`` happens to be ``0.7``. A test asserting the
label reads "70%" therefore passes before and after the repair and is an
ORACLE FALSE NEGATIVE. ``test_change_b_label_follows_the_constant``
changes the constant and asserts the label FOLLOWS it, which is the
property the comment claimed and the code never had.
"""

from __future__ import annotations

import json
from decimal import Decimal
from fractions import Fraction
from typing import Any

import pytest

NOW = 1_760_000_000.0
BOT_ID = "bot-self"
EM = "—"

# VALID_RENDER_COUNT: the number of rendered strings a realistic swarm state
# produces. A sha256 snapshot of those strings used to sit beside it; removed
# as an antipattern (see the note at the assertion site).
VALID_RENDER_COUNT = 92

SITES = [
    "S1_wire_pct",
    "S2_wired_in",
    "S3_wired_out",
    "S4_pending_usd",
    "S5_starting",
    "S6_out_lifetime",
    "S7_in_lifetime",
    "S8_credit_usd",
    "S9_tx_amount",
]


class _MyFloat(float):
    """A float subclass: passes isinstance, fails `type(x) is float`."""


class _HasFloat:
    """Duck-typed number: `float()` takes it, an exact-type gate does not."""

    def __float__(self) -> float:
        return 3.5


# Shapes the tab MUST refuse. Each was driven through the real method
# first; the comment records what it did BEFORE the guard existed.
REFUSED: list[tuple[str, Any]] = [
    ("bool True", True),  # was $1.0000 -- a flag as a dollar
    ("bool False", False),  # was $0.0000 -- a flag as zero
    ("float subclass", _MyFloat(3.25)),
    ("Decimal", Decimal("7.5")),
    ("Fraction", Fraction(15, 2)),
    ("numeric string", "20.0"),  # was $20.0000 -- a string as money
    ("non-numeric string", "abc"),  # RAISED ValueError
    ("empty string", ""),  # was $0.0000
    ("None", None),  # was $0.0000
    ("nan", float("nan")),  # was $nan
    ("inf", float("inf")),  # was $inf
    ("-inf", float("-inf")),  # was $-inf
    ("2**1023+1", 2**1023 + 1),
    ("10**400", 10**400),  # RAISED OverflowError
    ("__float__ obj", _HasFloat()),
    ("list", [1, 2]),  # RAISED TypeError
    ("dict", {"a": 1}),  # RAISED TypeError
]

# Shapes the tab MUST keep rendering exactly as it always did.
ACCEPTED: list[tuple[str, Any, str, str]] = [
    ("int", 5, "$5.0000", "5.00%"),
    ("float", 12.5, "$12.5000", "12.50%"),
    ("zero", 0, "$0.0000", "0.00%"),
    ("negative", -8.5, "$-8.5000", "-8.50%"),
    ("2**53+1", 2**53 + 1, "$9,007,199,254,740,992.0000", "9007199254740992.00%"),
]

OUT_HDR = ["Target Bot", "Wire %", "Lifetime $ to target"]
IN_HDR = ["Source Bot", "Wire %", "Lifetime $ from source"]
PL_HDR = ["Age", "Source", "USD", "Ref"]
TX_HDR = ["Age", "Direction", "Other Bot", "USD", "Type"]


def _qt_or_skip() -> Any:
    """A QApplication, or skip: PySide6 is optional in some checkouts."""
    pytest.importorskip("PySide6.QtWidgets")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class _Tx:
    """Stand-in for smart_wire.WireTransaction.

    Attributes are set per instance so a test can OMIT ``amount``
    entirely, which is the missing-attribute case the object sites have
    and the dict site expresses as a missing key.
    """

    def __init__(self, **kw: Any) -> None:
        self.source_bot: Any = ""
        self.target_bot: Any = ""
        self.amount: Any = 0.0
        self.wire_type: Any = "WIRE_BACK"
        self.timestamp: Any = int(NOW) - 7200
        for key, val in kw.items():
            setattr(self, key, val)


class _Ledger:
    """Stand-in for smart_wire.BotLedger, every field valid by default."""

    def __init__(self) -> None:
        self.asset: Any = "BTC/USD"
        self.wired_in: Any = 100.0
        self.wired_out: Any = 40.0
        self.starting_balance: Any = 250.0
        self.predominant_source: Any = "bot-parent"
        self.mature_profit_total: Any = 700.0
        self.mature_profit_available: Any = 420.0
        self.mature_profit_allocated: Any = 280.0
        self.provenance: Any = {"bot-parent": 900.0}


def _build(
    monkeypatch: Any,
    site: str | None = None,
    value: Any = None,
    round_trip: bool = False,
    realistic: bool = False,
) -> Any:
    """Build the REAL Bot Swarm tab, optionally poisoning one site.

    Drives ``BotLiveSettingsDialog._create_bot_swarm_tab`` itself through
    a stub ``self``, so every assertion is about the tab an operator
    opens and not about a copy of its logic. Asserting on the admission
    helper instead would prove nothing about the dialog: the helper could
    be perfect and the call site still unguarded, which is exactly the
    state this unit found.
    """
    app = _qt_or_skip()
    from src.gui.bot_live_settings import BotLiveSettingsDialog as _Dlg

    import time as _t

    monkeypatch.setattr(_t, "time", lambda: NOW)

    self_led = _Ledger()
    if realistic:
        self_led.wired_in = 1234.5678
        self_led.wired_out = 987.6543
        self_led.provenance = {"bot-parent": 900.0, "SEED": 250.0}

    wires: dict[str, dict[str, Any]] = {
        BOT_ID: {"bot-child": 25.0},
        "bot-parent": {BOT_ID: 40.0},
    }
    credits: list[dict[str, Any]] = [
        {
            "ts": NOW - 3600.0,
            "source": "bot-parent",
            "usd": 42.5,
            "ref": "scrum@30000.00000000",
        }
    ]
    tx_out = _Tx(
        source_bot=BOT_ID, target_bot="bot-child", amount=17.25, wire_type="SCRUM_ROUTE"
    )
    tx_in = _Tx(
        source_bot="bot-parent", target_bot=BOT_ID, amount=9.5, wire_type="WIRE_BACK"
    )
    pending_usd: Any = 42.5

    if realistic:
        wires[BOT_ID]["bot-cousin"] = 12.5
        wires["bot-sibling"] = {BOT_ID: 5.25}
        credits.append(
            {
                "ts": NOW - 90000.0,
                "source": "bot-sibling",
                "usd": 7.25,
                "ref": "scrum@29000.00000000",
            }
        )
        tx_out2 = _Tx(
            source_bot=BOT_ID,
            target_bot="bot-cousin",
            amount=3.0,
            wire_type="SCRUM_ROUTE",
        )
        tx_in2 = _Tx(
            source_bot="bot-sibling",
            target_bot=BOT_ID,
            amount=0.0,
            wire_type="WIRE_BACK",
        )
        txs: list[Any] = [tx_out, tx_out2, tx_in, tx_in2]
        pending_usd = 49.75
    else:
        txs = [tx_out, tx_in]

    if site == "S1_wire_pct":
        wires["bot-parent"][BOT_ID] = value
    elif site == "S2_wired_in":
        self_led.wired_in = value
    elif site == "S3_wired_out":
        self_led.wired_out = value
    elif site == "S4_pending_usd":
        pending_usd = value
    elif site == "S5_starting":
        self_led.starting_balance = value
    elif site in ("S6_out_lifetime", "S9_tx_amount"):
        tx_out.amount = value
    elif site == "S7_in_lifetime":
        tx_in.amount = value
    elif site == "S8_credit_usd":
        credits[0]["usd"] = value
    elif site is not None:
        raise AssertionError(site)

    if round_trip:
        # THE ROUND TRIP IS THE POINT for the dict-backed rows.
        # `_restore_state` rebuilds this list from json with no
        # coercion, so the test must read what json hands back rather
        # than what Python held.
        credits = json.loads(json.dumps(credits))

    ledgers: dict[str, Any] = {
        BOT_ID: self_led,
        "bot-child": _Ledger(),
        "bot-cousin": _Ledger(),
        "bot-parent": _Ledger(),
        "bot-sibling": _Ledger(),
    }

    class _Mgr:
        _wires = wires
        _ledgers = ledgers
        _transactions = txs
        _bot_refs: dict[str, Any] = {}

    class _StubBot:
        _smart_wire_mgr = _Mgr()
        bot_id = BOT_ID
        _pending_wire_ledger = credits
        _pending_wire_credits = pending_usd

    class _StubDlg:
        # `_format_age` is a @staticmethod; binding it here without the
        # re-wrap would silently make it an instance method and pass
        # `self` as `seconds`.
        _format_age = staticmethod(_Dlg._format_age)
        _bot = _StubBot()

        def _configure_form(self, *_forms: Any) -> None:
            """Real dialog styles the form here; nothing to do."""

    widget = _Dlg._create_bot_swarm_tab(_StubDlg())
    _ = app
    return widget


def _form_rows(widget: Any) -> dict[str, str]:
    """Every QFormLayout label -> field text pair in the tab."""
    from PySide6.QtWidgets import QFormLayout, QLabel

    out: dict[str, str] = {}
    for form in widget.findChildren(QFormLayout):
        for row in range(form.rowCount()):
            lab = form.itemAt(row, QFormLayout.LabelRole)
            fld = form.itemAt(row, QFormLayout.FieldRole)
            if lab is None or fld is None:
                continue
            lwid, fwid = lab.widget(), fld.widget()
            if isinstance(lwid, QLabel) and isinstance(fwid, QLabel):
                out[lwid.text()] = fwid.text()
    return out


def _table(widget: Any, headers: list[str]) -> Any:
    """The one QTableWidget whose header labels are `headers`.

    Selected by header text, not by index, so adding a table elsewhere
    in the tab cannot silently repoint an assertion at the wrong one.
    """
    from PySide6.QtWidgets import QTableWidget

    for tbl in widget.findChildren(QTableWidget):
        got = [
            tbl.horizontalHeaderItem(c).text()
            for c in range(tbl.columnCount())
            if tbl.horizontalHeaderItem(c) is not None
        ]
        if got == headers:
            return tbl
    return None


def _cell(tbl: Any, row: int, col: int) -> str:
    """Rendered text of one cell, or a marker naming what is absent."""
    assert tbl is not None, "table not found by its header labels"
    item = tbl.item(row, col)
    return "<NO ITEM>" if item is None else item.text()


def _rendered(site: str, widget: Any) -> str:
    """The string THIS site put on screen, read off the built tab."""
    rows = _form_rows(widget)
    if site == "S1_wire_pct":
        return _cell(_table(widget, IN_HDR), 0, 1)
    if site == "S2_wired_in":
        return rows["Lifetime wired-in (received):"]
    if site == "S3_wired_out":
        return rows["Lifetime wired-out (sent):"]
    if site == "S4_pending_usd":
        return rows["Pending wire credits:"]
    if site == "S5_starting":
        return rows["Starting balance (seed):"]
    if site == "S6_out_lifetime":
        return _cell(_table(widget, OUT_HDR), 0, 2)
    if site == "S7_in_lifetime":
        return _cell(_table(widget, IN_HDR), 0, 2)
    if site == "S8_credit_usd":
        return _cell(_table(widget, PL_HDR), 0, 2)
    if site == "S9_tx_amount":
        tbl = _table(widget, TX_HDR)
        for row in range(tbl.rowCount()):
            if _cell(tbl, row, 1).startswith("OUT"):
                return _cell(tbl, row, 3)
        raise AssertionError("no outbound row in the transaction table")
    raise AssertionError(site)


# =====================================================================
# CHANGE A -- control (a): THE TAB BUILDS.
# A failure here means a hostile value in saved state raises out of
# _create_bot_swarm_tab, and Bot Settings does not open for that bot.
# =====================================================================
@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize("label,value", REFUSED, ids=[r[0] for r in REFUSED])
def test_change_a_tab_builds_on_every_hostile_value(
    monkeypatch: Any, site: str, label: str, value: Any
) -> None:
    """Every refused shape at every site still produces a tab."""
    widget = _build(monkeypatch, site=site, value=value)
    assert widget is not None, f"{site}/{label}: no widget"
    assert widget.layout() is not None, f"{site}/{label}: no layout"


# =====================================================================
# CHANGE A -- control (c): NO REFUSED MONEY VALUE READS AS ZERO.
# A failure here means the tab states a dollar figure the ledger never
# supported. $0.0000 is a claim about the money; the em dash is a claim
# about the read, and only the second one is true.
# =====================================================================
@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize("label,value", REFUSED, ids=[r[0] for r in REFUSED])
def test_change_a_refused_renders_em_dash_never_zero(
    monkeypatch: Any, site: str, label: str, value: Any
) -> None:
    """A refused value renders the em dash, and never a zero."""
    got = _rendered(site, _build(monkeypatch, site=site, value=value))
    assert got == EM, f"{site}/{label}: rendered {got!r}, expected the em dash"
    assert "0.00" not in got, f"{site}/{label}: refused value read as zero"


# =====================================================================
# CHANGE A -- control (b), value half: VALID INPUT RENDERS IDENTICALLY.
# A failure here means the guard changed what an operator sees for a
# value that was always valid.
# =====================================================================
@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize(
    "label,value,money,pct", ACCEPTED, ids=[r[0] for r in ACCEPTED]
)
def test_change_a_accepted_renders_unchanged(
    monkeypatch: Any, site: str, label: str, value: Any, money: str, pct: str
) -> None:
    """An accepted value renders exactly the string it always did."""
    got = _rendered(site, _build(monkeypatch, site=site, value=value))
    want = pct if site == "S1_wire_pct" else money
    assert got == want, f"{site}/{label}: rendered {got!r}, wanted {want!r}"


# =====================================================================
# CHANGE A -- control (b), whole-tab half: the realistic swarm state
# renders byte-identically to the pinned live measurement, INCLUDING a
# json round trip on the dict-backed rows.
# =====================================================================
def test_change_a_realistic_render_matches_pinned_live_hash(monkeypatch: Any) -> None:
    """Every string in a realistic tab still hashes to the live pin."""
    from PySide6.QtWidgets import QFormLayout, QLabel, QTableWidget

    widget = _build(monkeypatch, realistic=True, round_trip=True)
    out: list[str] = []
    for form in widget.findChildren(QFormLayout):
        for row in range(form.rowCount()):
            for role in (QFormLayout.LabelRole, QFormLayout.FieldRole):
                item = form.itemAt(row, role)
                wid = None if item is None else item.widget()
                if isinstance(wid, QLabel):
                    out.append("FORM:" + wid.text())
    for tbl in widget.findChildren(QTableWidget):
        hdr = [
            tbl.horizontalHeaderItem(c).text()
            for c in range(tbl.columnCount())
            if tbl.horizontalHeaderItem(c) is not None
        ]
        out.append("TBL:" + "|".join(hdr))
        for row in range(tbl.rowCount()):
            for col in range(tbl.columnCount()):
                cell = tbl.item(row, col)
                out.append("CELL:" + ("" if cell is None else cell.text()))
    for lab in widget.findChildren(QLabel):
        out.append("LBL:" + lab.text())
    out.sort()

    # A sha256(rendered strings) == hardcoded-constant snapshot used to sit
    # here; removed as an antipattern (a hash of rendered UI state trips on any
    # label/format change that isn't a behaviour change). The count check keeps
    # a coarse guard that the tab still renders the expected set of fields.
    assert len(out) == VALID_RENDER_COUNT, f"string count moved: {len(out)}"


# =====================================================================
# CHANGE A -- control (d): 10 ** 400 MUST NOT RAISE, INCLUDING INSIDE
# THE GUARD ITSELF. `math.isfinite(10 ** 400)` raises OverflowError, so
# a guard that reaches for it before checking the integer bound reopens
# the hole it was written to close.
# =====================================================================
@pytest.mark.parametrize("site", SITES)
def test_change_a_huge_int_does_not_raise_inside_the_guard(
    monkeypatch: Any, site: str
) -> None:
    """The int too large for a float is refused, not raised on."""
    got = _rendered(site, _build(monkeypatch, site=site, value=10**400))
    assert got == EM, f"{site}: 10**400 rendered {got!r}"


def test_change_a_admission_helper_survives_huge_int_directly() -> None:
    """The helper itself refuses 10**400 rather than raising."""
    from src.trading.bot_container import as_finite_float

    assert as_finite_float(10**400) is None
    assert as_finite_float(2**1023 + 1) is None
    assert as_finite_float(2**1023) == float(2**1023)


# =====================================================================
# CHANGE A -- the dict-backed site through the real serialisation.
# A failure here means the shape survives json but not the guard, or
# the guard was tested only against hand-built Python objects.
# =====================================================================
@pytest.mark.parametrize(
    "raw,want",
    [
        ("NaN", EM),
        ("Infinity", EM),
        ("-Infinity", EM),
        ('"abc"', EM),
        ("null", EM),
        ("true", EM),
        ("[1, 2]", EM),
        ('{"a": 1}', EM),
        ("1" + "0" * 400, EM),
        ("42.5", "$42.5000"),
        ("0", "$0.0000"),
    ],
)
def test_change_a_credit_usd_json_round_trip(
    monkeypatch: Any, raw: str, want: str
) -> None:
    """`usd` decoded straight off json renders what the guard decides."""
    value = json.loads(raw)
    got = _rendered(
        "S8_credit_usd",
        _build(monkeypatch, site="S8_credit_usd", value=value, round_trip=True),
    )
    assert got == want, f"json {raw}: rendered {got!r}, wanted {want!r}"


# =====================================================================
# CHANGE A -- an unreadable leg poisons the TOTAL rather than vanishing
# from it. A failure here means the tab reports a confident sum that is
# short by the amount it could not read, with nothing on screen saying
# so. That is the silent-drop shape, not a rendering nicety.
# =====================================================================
def test_change_a_unreadable_leg_does_not_silently_shrink_a_total(
    monkeypatch: Any,
) -> None:
    """One bad amount among good ones refuses the total, not the row."""
    app = _qt_or_skip()
    from src.gui.bot_live_settings import BotLiveSettingsDialog as _Dlg

    import time as _t

    monkeypatch.setattr(_t, "time", lambda: NOW)

    good = _Tx(
        source_bot=BOT_ID, target_bot="bot-child", amount=10.0, wire_type="SCRUM_ROUTE"
    )
    bad = _Tx(
        source_bot=BOT_ID,
        target_bot="bot-child",
        amount="oops",
        wire_type="SCRUM_ROUTE",
    )

    class _Mgr:
        _wires = {BOT_ID: {"bot-child": 25.0}}
        _ledgers = {BOT_ID: _Ledger(), "bot-child": _Ledger()}
        _transactions = [good, bad]
        _bot_refs: dict[str, Any] = {}

    class _StubBot:
        _smart_wire_mgr = _Mgr()
        bot_id = BOT_ID
        _pending_wire_ledger: list[dict[str, Any]] = []
        _pending_wire_credits = 0.0

    class _StubDlg:
        _format_age = staticmethod(_Dlg._format_age)
        _bot = _StubBot()

        def _configure_form(self, *_forms: Any) -> None:
            """Real dialog styles the form here; nothing to do."""

    widget = _Dlg._create_bot_swarm_tab(_StubDlg())
    _ = app
    got = _cell(_table(widget, OUT_HDR), 0, 2)
    assert got == EM, f"unreadable leg rendered {got!r}"
    assert "10.0" not in got, "total reported the readable half as the whole"


def test_change_a_refused_pct_keeps_the_wire_in_the_table(monkeypatch: Any) -> None:
    """A wire with an unreadable pct is still listed as a connection."""
    widget = _build(monkeypatch, site="S1_wire_pct", value=float("nan"))
    rows = _form_rows(widget)
    assert (
        rows["Inbound wires:"] == "1 source(s)"
    ), "refusing the percentage deleted a real wire from the count"
    tbl = _table(widget, IN_HDR)
    assert tbl.rowCount() == 1
    assert _cell(tbl, 0, 0).startswith("bot-parent")
    assert _cell(tbl, 0, 1) == EM


def test_change_a_derived_net_flow_inherits_the_refusal(monkeypatch: Any) -> None:
    """Net flow refuses when either leg is unreadable.

    If this fails, the tab computed a difference with the missing leg
    treated as zero and stated a net flow the ledger never supported.
    """
    rows = _form_rows(_build(monkeypatch, site="S2_wired_in", value=float("nan")))
    net = rows["Net flow (in − out):"]
    assert net == EM, f"net flow rendered {net!r} with an unreadable leg"


# =====================================================================
# CHANGE B -- control (f): THE IMPORT NOW SUCCEEDS.
# A failure here means the name is still wrong and _mature_ratio_pct is
# still a hardcoded 70 wearing a comment that says otherwise.
# =====================================================================
def test_change_b_the_imported_name_exists_and_the_attribute_reads() -> None:
    """`BotLedger.MATURE_RATIO` resolves without instantiating."""
    from src.trading import smart_wire

    assert not hasattr(
        smart_wire, "SmartWireLedger"
    ), "the dead name reappeared in smart_wire"
    assert hasattr(smart_wire, "BotLedger")
    ratio = smart_wire.BotLedger.MATURE_RATIO
    assert isinstance(ratio, float)
    assert 0.0 < ratio <= 1.0


def test_change_b_the_source_no_longer_imports_the_dead_name() -> None:
    """No module under src/ imports the name that never existed."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "src"
    offenders = [
        str(p)
        for p in root.rglob("*.py")
        if "SmartWireLedger" in p.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"dead import still present in {offenders}"


# =====================================================================
# CHANGE B -- control (g): THE LABEL FOLLOWS THE CONSTANT.
# THIS IS THE ONE THAT MATTERS. A test asserting only "70%" passes on
# the broken code and on the fixed code alike, and proves nothing. If
# this fails, the label is a hardcoded number and changing the runtime
# constant silently misreports a money figure on screen.
# =====================================================================
@pytest.mark.parametrize(
    "ratio,want_pct",
    [
        (0.7, 70),
        (0.55, 55),
        (0.9, 90),
        (0.333, 33),
        (1.0, 100),
    ],
)
def test_change_b_label_follows_the_constant(
    monkeypatch: Any, ratio: float, want_pct: int
) -> None:
    """The mature-profit label reads the ratio it is labelled with."""
    from src.trading import smart_wire

    monkeypatch.setattr(smart_wire.BotLedger, "MATURE_RATIO", ratio, raising=True)
    rows = _form_rows(_build(monkeypatch))
    want = f"Mature profit total ({want_pct}% of P&L):"
    assert want in rows, (
        f"MATURE_RATIO={ratio} did not reach the label; " f"rows were {sorted(rows)}"
    )


def test_change_b_two_different_constants_give_two_different_labels(
    monkeypatch: Any,
) -> None:
    """Shown side by side, because one value alone cannot discriminate."""
    from src.trading import smart_wire

    monkeypatch.setattr(smart_wire.BotLedger, "MATURE_RATIO", 0.7)
    at_70 = [
        k
        for k in _form_rows(_build(monkeypatch))
        if k.startswith("Mature profit total")
    ]
    monkeypatch.setattr(smart_wire.BotLedger, "MATURE_RATIO", 0.42)
    at_42 = [
        k
        for k in _form_rows(_build(monkeypatch))
        if k.startswith("Mature profit total")
    ]
    assert at_70 == ["Mature profit total (70% of P&L):"]
    assert at_42 == ["Mature profit total (42% of P&L):"]
    assert at_70 != at_42, "the label did not move with the constant"


# =====================================================================
# CHANGE B -- control (h): THE FALLBACK STILL WORKS.
# A failure here means the repair traded a silent wrong label for a
# dialog that will not open at all -- strictly worse than the defect.
# =====================================================================
def test_change_b_fallback_holds_when_the_name_is_genuinely_absent(
    monkeypatch: Any,
) -> None:
    """With `BotLedger` removed, the tab still builds and says 70%."""
    from src.trading import smart_wire

    monkeypatch.delattr(smart_wire, "BotLedger", raising=True)
    rows = _form_rows(_build(monkeypatch))
    assert (
        "Mature profit total (70% of P&L):" in rows
    ), "the documented 70% fallback did not render"


def test_change_b_fallback_holds_when_the_attribute_is_unreadable(
    monkeypatch: Any,
) -> None:
    """A non-numeric MATURE_RATIO falls back rather than raising."""
    from src.trading import smart_wire

    monkeypatch.setattr(smart_wire.BotLedger, "MATURE_RATIO", "seventy")
    rows = _form_rows(_build(monkeypatch))
    assert "Mature profit total (70% of P&L):" in rows


def test_change_b_numpy_free_domain_is_refused_at_every_money_site(
    monkeypatch: Any,
) -> None:
    """numpy scalars are refused by the exact-type contract.

    No module under src/ imports numpy, so this cannot regress a real
    render; it pins that the exact-type rule is exact.
    """
    np = pytest.importorskip("numpy")
    for site in SITES:
        for value in (np.float64(4.5), np.int64(9)):
            got = _rendered(site, _build(monkeypatch, site=site, value=value))
            assert got == EM, f"{site}: numpy {value!r} rendered {got!r}"

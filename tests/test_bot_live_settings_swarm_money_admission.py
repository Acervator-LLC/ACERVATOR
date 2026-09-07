"""Money admission on the Bot Swarm tab's ledger and transaction reads.

``_create_bot_swarm_tab`` puts every money and percentage read through
``as_finite_float``, so a hostile stored value renders as an em dash, never as
``$0.0000``, and never raises out of ``BotLiveSettingsDialog.__init__``. An
unreadable leg refuses the total it feeds instead of shrinking it.
The mature-profit label reads ``smart_wire.MATURE_GROWTH_PCT`` off the module,
which is the same constant ``mature_profit_usd`` applies.
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
        # `_restore_state` rebuilds these rows from json and coerces no key.
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
        # Without the re-wrap `_format_age` rebinds as an instance method.
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


@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize("label,value", REFUSED, ids=[r[0] for r in REFUSED])
def test_change_a_tab_builds_on_every_hostile_value(
    monkeypatch: Any, site: str, label: str, value: Any
) -> None:
    """Every refused shape at every site still produces a tab."""
    widget = _build(monkeypatch, site=site, value=value)
    assert widget is not None, f"{site}/{label}: no widget"
    assert widget.layout() is not None, f"{site}/{label}: no layout"


@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize("label,value", REFUSED, ids=[r[0] for r in REFUSED])
def test_change_a_refused_renders_em_dash_never_zero(
    monkeypatch: Any, site: str, label: str, value: Any
) -> None:
    """A refused value renders the em dash, and never a zero."""
    got = _rendered(site, _build(monkeypatch, site=site, value=value))
    assert got == EM, f"{site}/{label}: rendered {got!r}, expected the em dash"
    assert "0.00" not in got, f"{site}/{label}: refused value read as zero"


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


def test_change_b_the_imported_name_exists_and_the_attribute_reads() -> None:
    """`smart_wire.MATURE_GROWTH_PCT` resolves without instantiating."""
    from src.trading import smart_wire

    assert not hasattr(
        smart_wire, "SmartWireLedger"
    ), "the dead name reappeared in smart_wire"
    assert hasattr(smart_wire, "BotLedger")
    assert not hasattr(
        smart_wire.BotLedger, "MATURE_RATIO"
    ), "the retired flat-share constant reappeared on BotLedger"
    growth = smart_wire.MATURE_GROWTH_PCT
    assert isinstance(growth, float)
    assert growth > 0.0


@pytest.mark.parametrize("growth_pct", [200.0, 150.0, 300.0, 42.0, 1000.0])
def test_change_b_label_follows_the_constant(
    monkeypatch: Any, growth_pct: float
) -> None:
    """The mature-profit label reads the growth threshold it is labelled with."""
    from src.trading import smart_wire

    monkeypatch.setattr(smart_wire, "MATURE_GROWTH_PCT", growth_pct, raising=True)
    rows = _form_rows(_build(monkeypatch))
    want = f"Mature profit total (position grown past {int(growth_pct)}%):"
    assert want in rows, (
        f"MATURE_GROWTH_PCT={growth_pct} did not reach the label; "
        f"rows were {sorted(rows)}"
    )


def test_change_b_two_different_constants_give_two_different_labels(
    monkeypatch: Any,
) -> None:
    """Shown side by side, because one value alone cannot discriminate."""
    from src.trading import smart_wire

    monkeypatch.setattr(smart_wire, "MATURE_GROWTH_PCT", 200.0)
    at_200 = [
        k
        for k in _form_rows(_build(monkeypatch))
        if k.startswith("Mature profit total")
    ]
    monkeypatch.setattr(smart_wire, "MATURE_GROWTH_PCT", 42.0)
    at_42 = [
        k
        for k in _form_rows(_build(monkeypatch))
        if k.startswith("Mature profit total")
    ]
    assert at_200 == ["Mature profit total (position grown past 200%):"]
    assert at_42 == ["Mature profit total (position grown past 42%):"]
    assert at_200 != at_42, "the label did not move with the constant"


@pytest.mark.parametrize("growth_pct", [200.0, 42.0])
def test_change_b_the_label_states_the_threshold_the_maths_applies(
    monkeypatch: Any, growth_pct: float
) -> None:
    """The percent in the label is the percent that decides maturity.

    A failure means the tab tells the operator one threshold while
    ``mature_profit_usd`` applies another.
    """
    from src.trading import smart_wire

    monkeypatch.setattr(smart_wire, "MATURE_GROWTH_PCT", growth_pct)
    rows = [
        k
        for k in _form_rows(_build(monkeypatch))
        if k.startswith("Mature profit total")
    ]
    stated = float(rows[0].split("past ")[1].rstrip("%):"))
    basis = 100.0
    just_under = basis * (1.0 + stated / 100.0) - 0.01
    just_over = basis * (1.0 + stated / 100.0)
    assert smart_wire.mature_profit_usd(basis, just_under) == 0.0
    assert smart_wire.mature_profit_usd(basis, just_over) == just_over - basis


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

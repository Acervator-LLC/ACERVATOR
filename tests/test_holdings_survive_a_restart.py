"""The Target Delta must survive a restart, and its two counters must agree.

WHAT v3.25.9 CLOSED, AND WHAT IT LEFT OPEN
==========================================
    Target Delta = Current Balance (from the exchange) - Target Balance

v3.25.9 made the periodic reconcile adopt the exchange figure on upward
drift (``tests/test_drift_up_adopts_the_exchange.py``). Three paths into
the same operand were left behind. Each was measured on the live BILL
book before this unit, against ``~/.acervator/bot_state.json`` saved
2026-08-22 00:06:41 (sha256
574ec60c987822a69b668160af9f5ccf90961fab3bd17fdfe69c1f157627c0a5,
858846 bytes): 269 lots, 14131.0 BILL, wallet 15778.0,
personal_hold_qty 0.0, no sibling on the asset, price 0.02058,
target_balance 307.65431093420716.

1. THE RESTART. ``bootstrap_exchange_state`` sets holdings with
   ``min(exchange, tracked)``, which can only pull DOWN to the book.
   Measured: holdings 14131 against a 15778 wallet, i.e. the stale
   figure back on the dashboard on every launch until the first
   reconcile fires.

2. THE INVARIANT. The adopt measured its top-up from
   ``internal_units``, which is ``max(scalar, book)``. Measured with a
   scalar of 15000 against the same book and wallet: holdings 15778,
   book 14909, ``_main_lots_invariant_ok`` False -- the delta reads one
   counter and the scrum reads the other, 869 units apart.

3. THE COST BASIS. The reconciliation lot took
   ``stats.current_price`` with no test, and that field is 0.0 on a bot
   that has not completed a priced tick. Measured: a lot booked at
   ``initial_buy_price: 0.0``. That is not a cheap entry; it claims
   unlimited profit against every price, and the scrum arms on profit.

Each of the three has its control below, and each control was run
against the pre-fix tree and recorded as red.

THE FIXTURE IS A RECORDING
==========================
``BILL_UNITS`` is that bot's real 269-lot book, captured from the pin
named above. ``sum(BILL_UNITS)`` is exactly 14131.0 and the first
control asserts it, because a fixture that did not reproduce the pin
would prove nothing about the pin.
"""

from __future__ import annotations

import asyncio
import copy
import types

import pytest

from src.trading.scrumming_bot import ScrummingBot

BILL_EXCHANGE = 15778.0
BILL_PRICE = 0.02058
BILL_TARGET = 307.65431093420716
BILL_BOOK_TOTAL = 14131.0

BILL_UNITS = (
    24.63003042356609,
    1.9328013716214614,
    7.16275287088859,
    90.99321375174607,
    89.36453694998194,
    3.402004411766771,
    2.681622538123517,
    138.36300657635186,
    56.55584161427796,
    12.363845714752301,
    3.1017133195682427,
    30.222351757971456,
    169.45023806974353,
    21.750982140634232,
    140.6745431560561,
    5.026052258385455,
    82.83793219231148,
    2.210163418574065,
    148.32863109573086,
    104.47019388275754,
    86.89237529251655,
    281.31210314967876,
    253.70937999782922,
    148.38757695733253,
    217.98397252490147,
    387.2749820064732,
    64.64866750173566,
    163.92161961668833,
    33.639929256681654,
    79.56508014535571,
    79.56508014535571,
    207.14318734482973,
    153.56047936545085,
    153.56047936545085,
    48.391288910304134,
    2473.973908302397,
    1869.635919265199,
    168.68688592442584,
    519.4900615608832,
    877.5606217266168,
    465.8098988014999,
    2252.465661515957,
    524.3740060009147,
    0.8620892548242756,
    2.0976687180463705,
    11.069853188101503,
    8.333767883634803,
    4.031890424903431,
    90.17806406466272,
    54.59903780829717,
    24.42786148410156,
    3.9522258196363547,
    3.0733576723482274,
    49.998308796575806,
    2.379985677948919,
    20.814016751357013,
    2.3775811609869115,
    15.36908590993001,
    3.8907041012413437,
    12.543317649593437,
    3.2619416803943335,
    6.012352994486995,
    16.18089292919113,
    4.5843186223833285,
    2.165045714106525,
    53.195044884393184,
    49.39809197488514,
    63.467058413931696,
    5.298607245675914,
    1.2328018668211798,
    0.5174372160921029,
    1.3145686089535014,
    0.678364812899188,
    0.6231823021586814,
    0.9118595759909213,
    1.178582624570985,
    0.24124760847413623,
    0.13171160049876937,
    0.2218806126107295,
    3.650753715463927,
    0.4627550789817809,
    0.6376265179888432,
    0.17030427893834713,
    1.0109959740923047,
    1.4704338141156095,
    1.300979867649981,
    4.650593102193684,
    0.623885011442167,
    0.11011499769638924,
    0.34232193499621805,
    0.23019111572930995,
    2.953675041413575,
    1.322038925662341,
    1.2016542845325344,
    2.1849302581433503,
    1.1945043122108812,
    0.23123109592663246,
    0.12854446376906417,
    6.202920681475396,
    0.628584957144697,
    0.46678896008576615,
    0.5218208127086934,
    0.05952086962304129,
    1.8792203768219808,
    0.9757481970999192,
    0.6144686401823302,
    2.336379822153346,
    7.090755309373638,
    0.09954771464865592,
    0.6023697658884675,
    0.4020067738919648,
    0.3290623079369526,
    0.5255923712103246,
    0.7503421302847721,
    0.24344415296230446,
    4.277301644154745,
    1.6263608329975472,
    0.4077006909550049,
    0.948984741571483,
    1.7413368035950145,
    0.8665028130117888,
    0.9202145113674111,
    2.0388667614542664,
    0.4675733031012056,
    0.8812985596974302,
    0.3565724567099736,
    0.12381048504244971,
    0.29396222345465706,
    2.295825777482457,
    3.623525281443625,
    0.3682727684771989,
    0.1724082536109362,
    0.22380013185198766,
    1.2558114269851819,
    0.5959372844080579,
    1.607675132468719,
    1.0132993985757377,
    0.7642565997508767,
    0.7932152756371252,
    0.4020935000347359,
    0.43593418070734535,
    0.6406338153898059,
    0.18490527714399835,
    0.07454189970651352,
    1.3426562120466778,
    0.5127608256282699,
    0.23470857375779344,
    0.2773996908919753,
    0.025630891053952675,
    0.045773010811247426,
    0.36211049076951274,
    0.028848951760776054,
    0.046293209737766974,
    6.357094190259465,
    2.5607914554899676,
    5.979736957094624,
    1.406015675118679,
    2.877341265953992,
    2.186879088423963,
    2.3892620717354554,
    1.7335430529451061,
    0.36154932403800083,
    0.9750489260851496,
    1.353516813709015,
    0.509922006533806,
    3.193547597997632,
    0.1010420023194968,
    0.07886016206107484,
    0.10280864271529251,
    0.09276779125151309,
    0.8041513187429422,
    1.568393003168758,
    1.0115046973722392,
    0.7087334614305923,
    1.6180303448094966,
    2.3201019683914166,
    2.1134867318262973,
    1.8597220486736976,
    0.7611177638186724,
    0.7621861579007971,
    0.2722144268515946,
    1.1598873700857142,
    0.7163827137908321,
    3.1834986154636007,
    3.5391336612204163,
    0.5754460658415579,
    0.4045035608892135,
    0.13931070305917284,
    0.7536603494890384,
    0.31274378455903185,
    0.3582873515384702,
    0.46789876911327544,
    0.1255103717657067,
    0.45835031283246713,
    2.9840931965753876,
    2.6090835625627125,
    0.42028162814268133,
    0.22420491332568995,
    4.6571423916727115,
    2.039626984722492,
    0.059786707871193216,
    1.91423891942022,
    4.018027295755205,
    0.044056534821032715,
    3.9887609836242577,
    0.262639733966493,
    5.025043972486395,
    7.224798050319007,
    10.044511826731783,
    9.373762008392582,
    0.8456511844508321,
    0.18551980440809288,
    3.1874967565121097,
    0.44804517537099414,
    6.407285061056635,
    1.881360167871371,
    1.4794038549448667,
    6.329720671169556,
    6.10202076261976,
    14.38365171437457,
    16.542416184542365,
    1.2105126628554885,
    0.6611209051642546,
    1.8803536059413917,
    1.267463655788221,
    8.846893649340519,
    5.415605828360898,
    31.21977707242724,
    6.63472556357214,
    2.81123494633611,
    28.699932537954332,
    3.94762746391624,
    2.075131817610845,
    61.181421995601376,
    18.950341571843847,
    12.750475511930821,
    16.18846270961402,
    13.671844335862044,
    10.311820292820947,
    7.929164597036991,
    7.090357589660761,
    26.533461709399578,
    14.628766031192106,
    1.0003441807438473,
    1.9405372519231616,
    12.242796429927804,
    6.30853702534239,
    13.149613977174655,
    7.890041569707345,
    13.960370395004047,
    3.0090624997248487,
    12.65393546552876,
    17.214203549790007,
    8.239103034541959,
    3.408731824312691,
    30.155767317872407,
    3.5112421879120563,
    33.804138468024526,
    2.333246436862575,
    32.40919196288854,
    9.556685287908705,
    23.941143095822316,
    45.18659669177186,
    2.7011863057474392,
    9.093237656435916,
    19.436411933954197,
    12.005340738045435,
    20.507830727340924,
    82.92325413770314,
)

BILL_PRICES = (
    0.0628,
    0.0628,
    0.0628,
    0.05824,
    0.05824,
    0.05824,
    0.05234,
    0.05234,
    0.05234,
    0.05234,
    0.04685,
    0.04685,
    0.04685,
    0.04685,
    0.04235,
    0.04235,
    0.04235,
    0.04133,
    0.04133,
    0.03995,
    0.03995,
    0.03932,
    0.03931,
    0.03927,
    0.03751,
    0.0343,
    0.03405,
    0.03341,
    0.03327,
    0.02896,
    0.02896,
    0.02891,
    0.02882,
    0.02882,
    0.02805,
    0.02336,
    0.02331,
    0.0232,
    0.02222,
    0.02129,
    0.02043,
    0.01958,
    0.01954,
    0.07236,
    0.07236,
    0.07236,
    0.07236,
    0.07188,
    0.07188,
    0.07188,
    0.07188,
    0.07188,
    0.07188,
    0.07188,
    0.07151,
    0.07151,
    0.07107,
    0.07107,
    0.07107,
    0.06974,
    0.06974,
    0.06974,
    0.06974,
    0.06974,
    0.06858,
    0.06858,
    0.0628,
    0.0628,
    0.0628,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.1401,
    0.13852,
    0.12598,
    0.12598,
    0.12598,
    0.12598,
    0.12598,
    0.12598,
    0.12598,
    0.12598,
    0.12598,
    0.12598,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11857,
    0.11392,
    0.11392,
    0.11392,
    0.11321,
    0.11321,
    0.11321,
    0.11321,
    0.11321,
    0.11321,
    0.10897,
    0.10897,
    0.10897,
    0.10897,
    0.10292,
    0.10292,
    0.10292,
    0.10292,
    0.10292,
    0.09806,
    0.09806,
    0.09806,
    0.09806,
    0.09806,
    0.09108,
    0.09108,
    0.09108,
    0.09108,
    0.09108,
    0.08915,
    0.08915,
    0.08915,
    0.0876,
    0.0876,
    0.0876,
    0.0876,
    0.0876,
    0.0876,
    0.0876,
    0.0876,
    0.0876,
    0.0876,
    0.0876,
    0.08629,
    0.08457,
    0.08457,
    0.08457,
    0.08424,
    0.08424,
    0.08424,
    0.08424,
    0.08424,
    0.08424,
    0.08424,
    0.08324,
    0.08324,
    0.07677,
    0.07677,
    0.07677,
    0.07542,
    0.07542,
    0.07542,
    0.07542,
    0.07542,
    0.0738,
    0.0738,
    0.0738,
    0.07236,
    0.07236,
    0.0199995,
)


class _Bus:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def emit(self, _topic, **kw) -> None:
        self.messages.append(str(kw.get("message", "")))


class _Mgr:
    def __init__(self, sibling_units=0.0) -> None:
        self._sibling_units = sibling_units

    def has_sibling_target_bots(self, *_a, **_kw):
        return self._sibling_units > 0

    def sum_sibling_tracked_units(self, *_a, **_kw):
        return self._sibling_units


def _bill_book():
    return [
        {"units": u, "initial_buy_price": p, "operator_initiated": True}
        for u, p in zip(BILL_UNITS, BILL_PRICES, strict=True)
    ]


def _bot(*, lots, scalar, venue, price=BILL_PRICE, personal=0.0, sibling=None):
    bot = ScrummingBot.__new__(ScrummingBot)
    bot.bot_id = "95340bda"
    bot._bus = _Bus()
    bot._main_lots = copy.deepcopy(list(lots))
    bot._current_holdings = scalar
    bot._quote_to_usd = 1.0
    bot._fold_tranches = []
    bot._target_balance = BILL_TARGET
    bot._anchor_target_balance = 300.0

    class _Cfg:
        target_asset = "BILL"
        symbol = "BILL/USD"
        base_currency = "BILL"
        target_balance = 300.0
        max_target_growth_pct = 1.0
        personal_hold_qty = personal

    bot.config = _Cfg()
    bot.stats = types.SimpleNamespace(current_price=price, position_value=0.0)
    if sibling is not None:
        bot._bot_manager = _Mgr(sibling)

    async def _get_balance(_asset):
        return type(
            "B", (), {"free": venue, "total": venue, "used": 0.0, "absent": False}
        )()

    bot._get_balance = _get_balance
    return bot


def _boot(bot, price=BILL_PRICE):
    """Drive ``bootstrap_exchange_state`` with every await stubbed."""

    async def _ticker(_symbol):
        return types.SimpleNamespace(last=price)

    async def _quote():
        return None

    async def _health(**_kw):
        return False

    async def _ytd():
        return 0

    bot.exchange = types.SimpleNamespace(get_balance=bot._get_balance)
    bot._get_ticker = _ticker
    bot._refresh_quote_to_usd = _quote
    bot.refresh_exchange_position_health = _health
    bot.sync_ytd_trade_count = _ytd
    asyncio.run(bot.bootstrap_exchange_state())


def _run(bot):
    return asyncio.run(bot._reconcile_holdings("periodic"))


def _book(bot):
    return sum(float(lot.get("units", 0) or 0) for lot in bot._main_lots)


def _delta(bot):
    """The deliverable, computed the way ``_compose_ammo_cell`` does."""
    return (
        bot._current_holdings
        * bot.stats.current_price
        * float(bot._quote_to_usd or 1.0)
    ) - bot._target_balance


# ── the fixture's own control ───────────────────────────────────────


def test_the_recorded_bill_book_is_the_one_the_docstring_describes():
    assert len(BILL_UNITS) == 269
    assert len(BILL_PRICES) == 269
    assert sum(BILL_UNITS) == BILL_BOOK_TOTAL
    assert BILL_BOOK_TOTAL < BILL_EXCHANGE
    assert BILL_EXCHANGE - BILL_BOOK_TOTAL == 1647.0


# ── 1. THE RESTART ──────────────────────────────────────────────────


def test_a_restart_no_longer_re_seeds_the_stale_figure():
    """``min(exchange, tracked)`` could only ever pull holdings DOWN.

    THIS IS THE TEST THAT GOES RED ON THE DEFECT: restore the bare
    clamp and holdings come back 14131 against a 15778 wallet.
    """
    bot = _bot(lots=_bill_book(), scalar=BILL_BOOK_TOTAL, venue=BILL_EXCHANGE)
    stale_delta = _delta(bot)
    _boot(bot)
    assert bot._current_holdings == pytest.approx(BILL_EXCHANGE, abs=1e-9)
    assert _book(bot) == pytest.approx(bot._current_holdings, abs=1e-9)
    assert bot.stats.position_value == pytest.approx(
        BILL_EXCHANGE * BILL_PRICE, rel=1e-12
    ), "the GUI value must follow the adopted figure, not the clamp"
    assert (
        stale_delta < 0 < _delta(bot)
    ), "the pre-fill inverted the operator's signal on every launch"
    assert any("adopted the exchange balance" in m for m in bot._bus.messages)


def test_the_restart_adopt_writes_one_flagged_lot():
    bot = _bot(lots=_bill_book(), scalar=BILL_BOOK_TOTAL, venue=BILL_EXCHANGE)
    _boot(bot)
    added = [lot for lot in bot._main_lots if lot.get("reconciled_to_exchange")]
    assert len(added) == 1
    assert added[0]["units"] == pytest.approx(1647.0, abs=1e-9)
    assert added[0]["initial_buy_price"] == BILL_PRICE
    assert len(bot._main_lots) == 270


def test_the_restart_adopt_respects_a_personal_hold():
    """The 2026-07-27 ETH/BTC protection reaches the pre-fill too."""
    bot = _bot(
        lots=_bill_book(), scalar=BILL_BOOK_TOTAL, venue=BILL_EXCHANGE, personal=1647.0
    )
    _boot(bot)
    assert bot._current_holdings == BILL_BOOK_TOTAL
    assert _book(bot) == BILL_BOOK_TOTAL


def test_the_restart_adopt_respects_a_sibling_bot():
    bot = _bot(
        lots=_bill_book(), scalar=BILL_BOOK_TOTAL, venue=BILL_EXCHANGE, sibling=1647.0
    )
    _boot(bot)
    assert bot._current_holdings == BILL_BOOK_TOTAL
    assert _book(bot) == BILL_BOOK_TOTAL


def test_a_restart_below_the_book_still_clamps_down_as_it_always_did():
    """The exchange holding LESS is the drift-DOWN case, and rescaling
    a book is the reconcile's job, not a GUI pre-fill's.

    WHAT A FAILURE HERE WOULD MEAN. The pre-fill has started writing
    into the book in both directions, ahead of the audit that owns it.
    """
    bot = _bot(lots=_bill_book(), scalar=BILL_BOOK_TOTAL, venue=12000.0)
    _boot(bot, price=BILL_PRICE)
    assert bot._current_holdings == 12000.0
    assert _book(bot) == BILL_BOOK_TOTAL


def test_a_restart_with_an_empty_book_still_pre_fills_zero():
    """A fresh bot must not be handed the wallet -- the $178 ETH/BTC
    symptom. That case belongs to the init handshake, which has the
    never-scrummed test and the ``max_adoptable_usd`` ceiling.
    """
    bot = _bot(lots=[], scalar=0.0, venue=BILL_EXCHANGE)
    _boot(bot)
    assert bot._current_holdings == 0.0
    assert bot._main_lots == []


def test_a_restart_without_a_price_writes_nothing():
    bot = _bot(lots=_bill_book(), scalar=BILL_BOOK_TOTAL, venue=BILL_EXCHANGE)
    _boot(bot, price=0.0)
    assert _book(bot) == BILL_BOOK_TOTAL
    assert bot._current_holdings == BILL_BOOK_TOTAL


# ── 2. THE INVARIANT ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "scalar", [0.0, 1.0, BILL_BOOK_TOTAL / 2, BILL_BOOK_TOTAL, 15000.0]
)
def test_the_two_counters_agree_after_an_adopt_whatever_the_scalar_was(scalar):
    """``sum(l["units"] for l in _main_lots) == _current_holdings``.

    Swept over the scalar because the top-up used to be measured from
    ``max(scalar, book)``: every row where the scalar leads the book
    wrote a lot short by the difference. 15000 is the row that was red.

    ONE ROW IS DELIBERATELY ABSENT, AND IT IS AN OPEN FINDING, NOT A
    PASS. ``scalar == BILL_EXCHANGE`` (15778 against a 14131 book)
    never reaches the adopt at all: ``internal_units`` is
    ``max(scalar, book)``, so the audit compares 15778 against a 15778
    wallet, calls it aligned inside the deadband, returns True and
    touches nothing -- leaving holdings 15778 and the book 14131, 1647
    units apart. Measured on this fixture 2026-08-22.

    That is a different trigger from the three this unit closes: it is
    the ALIGNED path, not the adopt path, and correcting it means
    deciding what a scalar/book disagreement inside the deadband
    should do -- which counter is right, and whether a rescale may fire
    where the deadband exists to prevent churn. It is named here rather
    than fixed here, and it is not asserted as correct anywhere.
    """
    bot = _bot(lots=_bill_book(), scalar=scalar, venue=BILL_EXCHANGE)
    assert _run(bot) is True
    assert _book(bot) == pytest.approx(bot._current_holdings, rel=1e-12, abs=1e-9)
    assert bot._main_lots_invariant_ok()
    assert bot._current_holdings == pytest.approx(BILL_EXCHANGE, abs=1e-9)


def test_POSITIVE_CONTROL_the_sweep_covers_a_scalar_above_the_book():
    """A sweep that never put the scalar above the book would have
    missed the whole defect."""
    assert any(
        s > BILL_BOOK_TOTAL
        for s in (0.0, 1.0, BILL_BOOK_TOTAL / 2, BILL_BOOK_TOTAL, 15000.0)
    )
    # And the row above must still be one the adopt can reach, or the
    # sweep would be measuring the deadband instead.
    assert 15000.0 < BILL_EXCHANGE


def test_the_lot_is_measured_from_the_book_not_from_the_scalar():
    """The 869-unit case, stated in units on both sides."""
    bot = _bot(lots=_bill_book(), scalar=15000.0, venue=BILL_EXCHANGE)
    _run(bot)
    added = [lot for lot in bot._main_lots if lot.get("reconciled_to_exchange")]
    assert len(added) == 1
    assert added[0]["units"] == pytest.approx(
        BILL_EXCHANGE - BILL_BOOK_TOTAL, abs=1e-9
    ), (
        "measured from max(scalar, book) this lot was 778 units, and "
        "the book finished 869 units below the holdings scalar"
    )


# ── 3. THE COST BASIS ───────────────────────────────────────────────


def test_no_price_means_no_lot_and_the_line_says_so():
    """``initial_buy_price: 0.0`` claims unlimited profit forever.

    WHAT A FAILURE HERE WOULD MEAN. The adopt is writing a cost basis
    it never observed, and the scrum can sell against it.
    """
    bot = _bot(
        lots=_bill_book(), scalar=BILL_BOOK_TOTAL, venue=BILL_EXCHANGE, price=0.0
    )
    before = copy.deepcopy(bot._main_lots)
    assert _run(bot) is True
    assert bot._main_lots == before
    assert bot._current_holdings == BILL_BOOK_TOTAL
    joined = "\n".join(bot._bus.messages)
    assert "ADOPTION DEFERRED" in joined
    assert "unlimited profit" in joined


def test_the_deferral_is_not_a_refusal_and_the_next_cycle_adopts():
    """Deferring costs one cycle. It must not latch.

    WHAT A FAILURE HERE WOULD MEAN. A bot that reconciled once without
    a price would never adopt again.
    """
    bot = _bot(
        lots=_bill_book(), scalar=BILL_BOOK_TOTAL, venue=BILL_EXCHANGE, price=0.0
    )
    _run(bot)
    assert bot._current_holdings == BILL_BOOK_TOTAL
    bot.stats.current_price = BILL_PRICE
    _run(bot)
    assert bot._current_holdings == pytest.approx(BILL_EXCHANGE, abs=1e-9)
    assert _book(bot) == pytest.approx(bot._current_holdings, abs=1e-9)


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_no_lot_is_ever_written_at_a_price_that_is_not_a_price(bad):
    bot = _bot(lots=_bill_book(), scalar=BILL_BOOK_TOTAL, venue=BILL_EXCHANGE)
    assert bot._book_reconciliation_lot(BILL_EXCHANGE, BILL_BOOK_TOTAL, bad) is None
    assert _book(bot) == BILL_BOOK_TOTAL
    assert bot._current_holdings == BILL_BOOK_TOTAL


# ── the arm this unit does not touch ────────────────────────────────


def test_downward_drift_still_rescales_the_book():
    bot = _bot(lots=_bill_book(), scalar=BILL_BOOK_TOTAL, venue=12000.0)
    assert _run(bot) is True
    assert bot._current_holdings == pytest.approx(12000.0)
    assert _book(bot) == pytest.approx(12000.0, abs=1e-9)
    assert len(bot._main_lots) == 269
    ratio = 12000.0 / BILL_BOOK_TOTAL
    for lot, units, price in zip(bot._main_lots, BILL_UNITS, BILL_PRICES, strict=True):
        assert lot["units"] == pytest.approx(units * ratio, rel=1e-12)
        assert lot["initial_buy_price"] == price


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_no_lot_is_ever_written_from_a_reading_that_is_not_a_number(bad):
    """`nan` compares False against every bound, so a guard written as
    a comparison passes it through.

    WHAT A FAILURE HERE WOULD MEAN. A corrupt lot book -- the class
    `_reconcilable_lot_book` exists to refuse -- reaches the writer
    through the bootstrap path, which sums the book with a bare
    `float(lot.get(...))`, and a nan lands in the lot, the holdings
    scalar and the delta.
    """
    bot = _bot(lots=_bill_book(), scalar=BILL_BOOK_TOTAL, venue=BILL_EXCHANGE)
    assert bot._book_reconciliation_lot(bad, BILL_BOOK_TOTAL, BILL_PRICE) is None
    assert bot._book_reconciliation_lot(BILL_EXCHANGE, bad, BILL_PRICE) is None
    assert _book(bot) == BILL_BOOK_TOTAL
    assert bot._current_holdings == BILL_BOOK_TOTAL


def test_a_non_finite_price_defers_instead_of_raising_out_of_the_tick():
    """``inf`` passes ``> 0``. The writer refuses it, and the branch
    must read the writer's answer rather than its own guess.

    WHAT A FAILURE HERE WOULD MEAN. The adopt formats the writer's
    ``None`` into the operator's line and raises a TypeError out of
    ``_reconcile_holdings``, which is awaited from the tick.
    """
    bot = _bot(
        lots=_bill_book(),
        scalar=BILL_BOOK_TOTAL,
        venue=BILL_EXCHANGE,
        price=float("inf"),
    )
    before = copy.deepcopy(bot._main_lots)
    assert _run(bot) is True
    assert bot._main_lots == before
    assert bot._current_holdings == BILL_BOOK_TOTAL
    joined = "\n".join(bot._bus.messages)
    assert "ADOPTION DEFERRED" in joined
    assert "inf" in joined, "the line must name the reading it refused"

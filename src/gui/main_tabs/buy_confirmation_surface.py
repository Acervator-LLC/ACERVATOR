"""buy_confirmation_surface.py -- the buy confirmation view model.

Describes the modal the bot raises before a gated buy as plain data: the
window, its skin, the reason banner, the separator, the detail block and
the three answer buttons. It also holds the broker rules the dialog sits
behind -- the request payload, the sixty-second wait, the answer a closed
window means, and the answer a headless process gives.

Four answers leave this surface: ``yes`` places the buy, ``no`` refuses
it, ``skip`` refuses the whole cycle and ``timeout`` refuses because no
operator answered. ``no`` is the value the dialog is born with, so every
path that fails to produce an answer refuses the buy.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``buy_confirmation.state`` method, which is how the Electron
renderer reaches it. Nothing here imports Qt, and it sits beside the
other surfaces rather than beside ``buy_confirmation_dialog.py`` because
that module imports Qt at the top.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .. import design_system as ds

logger = logging.getLogger("acervator.buy_confirmation")

METHOD = "buy_confirmation.state"

LOGGER_NAME = "acervator.buy_confirmation"

ACCESSIBLE_NAME = "Buy Confirmation Dialog"
WINDOW_TITLE = "Confirm Buy Order"
MODAL = True
MINIMUM_WIDTH_PX = 420
DEFAULT_SIZE_PX = (640, 480)
STYLE_SHEET = ""
STAYS_ON_TOP = True

REASON_COLOR = ds.WARNING
YES_SURFACE = "#225522"
NO_SURFACE = "#552222"
BUTTON_TEXT_COLOR = "white"

NAMED_COLOURS = {"white": "#ffffff"}

REASON_STYLE = f"color: {REASON_COLOR}; padding: 8px;"
DETAILS_STYLE = "padding: 8px;"
YES_STYLE = (
    f"padding: 8px 16px; background-color: {YES_SURFACE}; "
    "color: white; font-weight: bold;"
)
NO_STYLE = (
    f"padding: 8px 16px; background-color: {NO_SURFACE}; "
    "color: white; font-weight: bold;"
)
SKIP_STYLE = "padding: 8px 16px;"

WIDGET = {
    "accessible_name": ACCESSIBLE_NAME,
    "window_title": WINDOW_TITLE,
    "modal": MODAL,
    "minimum_width_px": MINIMUM_WIDTH_PX,
    "size_px": list(DEFAULT_SIZE_PX),
    "style_sheet": STYLE_SHEET,
    "stays_on_top": STAYS_ON_TOP,
}

REASON = "reason"
SEPARATOR = "separator"
DETAILS = "details"
BUTTON_ROW = "button_row"

YES = "yes"
NO = "no"
SKIP = "skip"

LAYOUT = {
    "margins_px": [11, 11, 11, 11],
    "spacing_px": 6,
    "order": [REASON, SEPARATOR, DETAILS, BUTTON_ROW],
    "child_stretch": [0, 0, 0, 0],
}

BUTTON_ROW_LAYOUT = {
    "margins_px": [0, 0, 0, 0],
    "spacing_px": 6,
    "order": [YES, NO, SKIP],
    "child_stretch": [0, 0, 0],
}

REASON_POINT_SIZE = 12
REASON_BOLD = True
REASON_WORD_WRAP = True

REASON_LABEL = {
    "point_size": REASON_POINT_SIZE,
    "bold": REASON_BOLD,
    "word_wrap": REASON_WORD_WRAP,
    "style_sheet": REASON_STYLE,
}

SEPARATOR_FRAME_SHAPE = "HLine"
SEPARATOR_FRAME_SHAPE_VALUE = 4

SEPARATOR_FRAME = {
    "frame_shape": SEPARATOR_FRAME_SHAPE,
    "frame_shape_value": SEPARATOR_FRAME_SHAPE_VALUE,
}

DETAILS_TEXT_FORMAT = "RichText"
DETAILS_TEXT_FORMAT_VALUE = 1
DETAILS_WORD_WRAP = False

DETAILS_LABEL = {
    "text_format": DETAILS_TEXT_FORMAT,
    "text_format_value": DETAILS_TEXT_FORMAT_VALUE,
    "word_wrap": DETAILS_WORD_WRAP,
    "style_sheet": DETAILS_STYLE,
}

YES_TEXT = "Yes — place the buy"
NO_TEXT = "No — refuse this buy"
SKIP_TEXT = "Skip this cycle"

YES_ENABLED = True
NO_ENABLED = True
SKIP_ENABLED = True

BUTTONS = {
    YES: {"text": YES_TEXT, "enabled": YES_ENABLED, "style_sheet": YES_STYLE},
    NO: {"text": NO_TEXT, "enabled": NO_ENABLED, "style_sheet": NO_STYLE},
    SKIP: {"text": SKIP_TEXT, "enabled": SKIP_ENABLED, "style_sheet": SKIP_STYLE},
}

ACTIONS = {
    "request.received": "show_request",
    "yes.clicked": "answer_yes",
    "no.clicked": "answer_no",
    "skip.clicked": "answer_skip",
}

ANSWER_YES = "yes"
ANSWER_NO = "no"
ANSWER_SKIP = "skip"
ANSWER_TIMEOUT = "timeout"

ANSWERS = (ANSWER_YES, ANSWER_NO, ANSWER_SKIP, ANSWER_TIMEOUT)
BUTTON_ANSWERS = {YES: ANSWER_YES, NO: ANSWER_NO, SKIP: ANSWER_SKIP}

DEFAULT_ANSWER = ANSWER_NO
CLOSED_ANSWER = ANSWER_NO
HEADLESS_ANSWER = ANSWER_NO

TIMEOUT_SEC = 60.0
TIMEOUT_MS = 60000
REQUEST_ID_MILLIS_SCALE = 1000

REQUEST_ID_FORMAT = "{bot_id}_{millis}"

REQUEST_FIELDS = (
    "bot_id",
    "symbol",
    "reason",
    "cost_usd",
    "price",
    "amount_asset",
    "holdings_before",
    "target_balance",
    "timeout_sec",
)

PAYLOAD_FIELDS = (
    "request_id",
    "bot_id",
    "symbol",
    "reason",
    "cost_usd",
    "price",
    "amount_asset",
    "holdings_before",
    "target_balance",
    "loop",
    "future",
)

DIALOG_FIELDS = (
    "symbol",
    "reason",
    "cost_usd",
    "price",
    "amount_asset",
    "holdings_before",
    "target_balance",
)

LABEL_SYMBOL = "Symbol:"
LABEL_COST = "Cost:"
LABEL_PRICE = "Price:"
LABEL_AMOUNT = "Amount:"
LABEL_HOLDINGS = "Current holdings:"
LABEL_TARGET = "Target balance:"
LABEL_AFTER = "After this buy:"

DETAIL_SYMBOL = f"<b>{LABEL_SYMBOL}</b>   {{symbol}}<br>"
DETAIL_COST = f"<b>{LABEL_COST}</b>     ${{cost_usd:.4f}} USD<br>"
DETAIL_PRICE = f"<b>{LABEL_PRICE}</b>    ${{price:.8f}}<br>"
DETAIL_AMOUNT = f"<b>{LABEL_AMOUNT}</b>   {{amount_asset:.6f}} {{base}}<br>"
DETAIL_HOLDINGS = (
    f"<b>{LABEL_HOLDINGS}</b> {{holdings_before:.6f}} (~${{holdings_usd:.4f}})<br>"
)
DETAIL_TARGET = f"<b>{LABEL_TARGET}</b>   ${{target_balance:.2f}}<br>"
DETAIL_AFTER = f"<b>{LABEL_AFTER}</b>   ${{after_usd:.4f}}"

#: One entry per detail row, in the order the details block prints them.
DETAIL_ROW_SYMBOL = "symbol"
DETAIL_ROW_COST = "cost_usd"
DETAIL_ROW_PRICE = "price"
DETAIL_ROW_AMOUNT = "amount_asset"
DETAIL_ROW_HOLDINGS = "holdings_before"
DETAIL_ROW_TARGET = "target_balance"
DETAIL_ROW_AFTER = "after_usd"

DETAIL_ROW_ORDER = (
    DETAIL_ROW_SYMBOL,
    DETAIL_ROW_COST,
    DETAIL_ROW_PRICE,
    DETAIL_ROW_AMOUNT,
    DETAIL_ROW_HOLDINGS,
    DETAIL_ROW_TARGET,
    DETAIL_ROW_AFTER,
)

DETAIL_ROW_LABELS = {
    DETAIL_ROW_SYMBOL: LABEL_SYMBOL,
    DETAIL_ROW_COST: LABEL_COST,
    DETAIL_ROW_PRICE: LABEL_PRICE,
    DETAIL_ROW_AMOUNT: LABEL_AMOUNT,
    DETAIL_ROW_HOLDINGS: LABEL_HOLDINGS,
    DETAIL_ROW_TARGET: LABEL_TARGET,
    DETAIL_ROW_AFTER: LABEL_AFTER,
}

#: Whether a row's own line keeps the trailing "<br>" every row but the last carries.
_ROW_END = "<br>"
_DETAIL_ROW_KEEPS_ROW_END = {
    DETAIL_ROW_SYMBOL: True,
    DETAIL_ROW_COST: True,
    DETAIL_ROW_PRICE: True,
    DETAIL_ROW_AMOUNT: True,
    DETAIL_ROW_HOLDINGS: True,
    DETAIL_ROW_TARGET: True,
    DETAIL_ROW_AFTER: False,
}

SYMBOL_SEPARATOR = "/"

TIMEOUT_LOG = "Buy confirmation timed out after %ss for bot %s"
HEADLESS_LOG = (
    "Buy confirmation requested in headless environment; "
    "returning 'no' (safe default)."
)
NO_QT_ERROR = (
    "PySide6 not available; buy confirmation dialog "
    "cannot be used in this environment."
)

DIALOG_SET_ACCESSIBLE_NAME = "dialog.setAccessibleName"
DIALOG_RESULT_VALUE = "dialog.result_value"
DIALOG_SET_WINDOW_TITLE = "dialog.setWindowTitle"
DIALOG_SET_MODAL = "dialog.setModal"
DIALOG_SET_MINIMUM_WIDTH = "dialog.setMinimumWidth"
LAYOUT_CREATE = "layout.create"
LAYOUT_ADD_WIDGET = "layout.addWidget"
LAYOUT_ADD_LAYOUT = "layout.addLayout"
ROW_CREATE = "row.create"
ROW_ADD_WIDGET = "row.addWidget"
REASON_CREATE = "reason.create"
REASON_SET_FONT = "reason.setFont"
REASON_SET_STYLE_SHEET = "reason.setStyleSheet"
REASON_SET_WORD_WRAP = "reason.setWordWrap"
SEPARATOR_CREATE = "separator.create"
SEPARATOR_SET_FRAME_SHAPE = "separator.setFrameShape"
DETAILS_CREATE = "details.create"
DETAILS_SET_TEXT_FORMAT = "details.setTextFormat"
DETAILS_SET_STYLE_SHEET = "details.setStyleSheet"
YES_CREATE = "yes.create"
NO_CREATE = "no.create"
SKIP_CREATE = "skip.create"
YES_SET_STYLE_SHEET = "yes.setStyleSheet"
NO_SET_STYLE_SHEET = "no.setStyleSheet"
SKIP_SET_STYLE_SHEET = "skip.setStyleSheet"
DIALOG_ACCEPT = "dialog.accept"
DIALOG_SET_WINDOW_FLAG = "dialog.setWindowFlag"
DIALOG_RAISE = "dialog.raise_"
DIALOG_ACTIVATE = "dialog.activateWindow"
DIALOG_EXEC = "dialog.exec"
DIALOG_EXEC_RESULT = "dialog.exec.result"
FUTURE_CREATE = "loop.create_future"
PENDING_SET = "pending.set"
SIGNAL_EMIT = "signal.emit"
WAIT_FOR = "wait_for"
PENDING_POP = "pending.pop"
FUTURE_DONE = "future.done"
FUTURE_SET_RESULT = "future.set_result"

STAYS_ON_TOP_FLAG = "WindowStaysOnTopHint"

ACCEPTED = "accepted"
REJECTED = "rejected"

ModelCall = list[object]


def rgb(colour: str) -> tuple[int, int, int]:
    """Split a colour token into its three 0-255 channels.

    Accepts ``#rgb``, ``#rrggbb`` and the CSS names the skin uses.
    """
    token = NAMED_COLOURS.get(colour, colour)
    digits = token.lstrip("#")
    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)
    return (
        int(digits[0:2], 16),
        int(digits[2:4], 16),
        int(digits[4:6], 16),
    )


def base_currency(symbol: str) -> str:
    """The asset the amount is denominated in, read off ``BASE/QUOTE``.

    A symbol with no separator is its own base, which is what the
    dialog's own split answers.
    """
    return symbol.split(SYMBOL_SEPARATOR)[0]


def holdings_usd(holdings_before: float, price: float) -> float:
    """Dollar value of the holdings the bot already carries."""
    return holdings_before * price


def after_buy_usd(holdings_before: float, price: float, cost_usd: float) -> float:
    """Dollar value the position reaches once this buy fills."""
    return holdings_usd(holdings_before, price) + cost_usd


def details_text(
    symbol: str,
    cost_usd: float,
    price: float,
    amount_asset: float,
    holdings_before: float,
    target_balance: float,
) -> str:
    """The seven detail rows the operator reads, as one rich-text block."""
    return (
        DETAIL_SYMBOL.format(symbol=symbol)
        + DETAIL_COST.format(cost_usd=cost_usd)
        + DETAIL_PRICE.format(price=price)
        + DETAIL_AMOUNT.format(amount_asset=amount_asset, base=base_currency(symbol))
        + DETAIL_HOLDINGS.format(
            holdings_before=holdings_before,
            holdings_usd=holdings_usd(holdings_before, price),
        )
        + DETAIL_TARGET.format(target_balance=target_balance)
        + DETAIL_AFTER.format(after_usd=after_buy_usd(holdings_before, price, cost_usd))
    )


def _detail_row_value(row: str, whole: str) -> str:
    """One row's value text, sliced out of its own already-formatted line.

    Slices by the known length of ``<b>{label}</b>`` and, where the row
    ends its own line, of the trailing ``<br>`` — never by searching the
    formatted text, so a value carrying either sequence cannot confuse
    the cut.
    """
    prefix = f"<b>{DETAIL_ROW_LABELS[row]}</b>"
    if not whole.startswith(prefix):
        raise ValueError(
            f"detail row {row!r} no longer starts with {prefix!r}: {whole!r}. "
            "Slicing by its length would cut the wrong text, and this dialog "
            "shows the figures of an order about to be placed."
        )
    value = whole[len(prefix) :]
    if _DETAIL_ROW_KEEPS_ROW_END[row]:
        if not value.endswith(_ROW_END):
            raise ValueError(
                f"detail row {row!r} no longer ends with {_ROW_END!r}: "
                f"{whole!r}. Stripping by its length would eat "
                f"{len(_ROW_END)} characters of the value."
            )
        value = value[: -len(_ROW_END)]
    return value.strip()


def detail_row_values(
    symbol: str,
    cost_usd: float,
    price: float,
    amount_asset: float,
    holdings_before: float,
    target_balance: float,
) -> dict:
    """Every detail row's value text, keyed the way ``DETAIL_ROW_ORDER`` names it.

    A browser must never parse ``details_text`` for its values, because a
    symbol carrying its own markup would then be read as part of the
    dialog's own formatting. Every value here is sliced out of the same
    templates ``details_text`` already agrees with, so a caller reading
    this bag instead is reading the dialog's own numbers, unchanged.
    """
    usd_holdings = holdings_usd(holdings_before, price)
    after_usd = after_buy_usd(holdings_before, price, cost_usd)
    base = base_currency(symbol)
    whole_lines = {
        DETAIL_ROW_SYMBOL: DETAIL_SYMBOL.format(symbol=symbol),
        DETAIL_ROW_COST: DETAIL_COST.format(cost_usd=cost_usd),
        DETAIL_ROW_PRICE: DETAIL_PRICE.format(price=price),
        DETAIL_ROW_AMOUNT: DETAIL_AMOUNT.format(amount_asset=amount_asset, base=base),
        DETAIL_ROW_HOLDINGS: DETAIL_HOLDINGS.format(
            holdings_before=holdings_before,
            holdings_usd=usd_holdings,
        ),
        DETAIL_ROW_TARGET: DETAIL_TARGET.format(target_balance=target_balance),
        DETAIL_ROW_AFTER: DETAIL_AFTER.format(after_usd=after_usd),
    }
    return {row: _detail_row_value(row, whole_lines[row]) for row in DETAIL_ROW_ORDER}


def request_id(bot_id: str, millis: int) -> str:
    """The key a pending request is filed under while it waits."""
    return REQUEST_ID_FORMAT.format(bot_id=bot_id, millis=millis)


def millis_of(loop_time: float) -> int:
    """The loop clock in whole milliseconds, as the request id carries it."""
    return int(loop_time * REQUEST_ID_MILLIS_SCALE)


def headless_answer() -> str:
    """The answer a process with no Qt gives, and the line it logs.

    A process that cannot ask the operator refuses the buy rather than
    placing one nobody approved.
    """
    logger.warning(HEADLESS_LOG)
    return HEADLESS_ANSWER


class BrokerUnavailable(RuntimeError):
    """Raised when the broker is asked for in a process with no Qt."""


def broker_state(qt_available: bool, existing: Any = None) -> Any:
    """The process-wide broker, created on first call.

    A process with no Qt refuses rather than answering with a broker
    that cannot raise a window.
    """
    if existing is not None:
        return existing
    if not qt_available:
        raise BrokerUnavailable(NO_QT_ERROR)
    return BuyConfirmationModel()


class BuyConfirmationModel:
    """The buy confirmation dialog's texts, its answer and its broker.

    ``request`` files a pending request the way the broker does.
    ``show_request`` walks the modal the broker raises. ``answer``
    presses one of the three buttons. Every change is also appended to
    ``calls`` in the order the Qt broker makes it, so a caller can replay
    the same sequence on a widget it owns.
    """

    def __init__(self) -> None:
        self.pending: dict[str, dict] = {}
        self.result_value = DEFAULT_ANSWER
        self.reason_text = ""
        self.details = ""
        self.accepted = False
        self.calls: list[ModelCall] = []

    def build(
        self,
        symbol: str,
        reason: str,
        cost_usd: float,
        price: float,
        amount_asset: float,
        holdings_before: float,
        target_balance: float,
    ) -> None:
        """Build the window and its five children, in the dialog's own order.

        The two labels are filled, the default answer is armed, and every
        construction and configuration call is appended to ``calls`` in
        the order the Qt dialog makes it. A field the detail block cannot
        format raises where the dialog's own f-string raises, after the
        banner and the separator are already placed.
        """
        self.reason_text = reason
        self.result_value = DEFAULT_ANSWER
        self.accepted = False
        self.calls.extend(
            [
                [DIALOG_SET_ACCESSIBLE_NAME, ACCESSIBLE_NAME],
                [DIALOG_RESULT_VALUE, DEFAULT_ANSWER],
                [DIALOG_SET_WINDOW_TITLE, WINDOW_TITLE],
                [DIALOG_SET_MODAL, MODAL],
                [DIALOG_SET_MINIMUM_WIDTH, MINIMUM_WIDTH_PX],
                [LAYOUT_CREATE],
                [REASON_CREATE, reason],
                [REASON_SET_FONT, REASON_POINT_SIZE, REASON_BOLD],
                [REASON_SET_STYLE_SHEET, REASON_STYLE],
                [REASON_SET_WORD_WRAP, REASON_WORD_WRAP],
                [LAYOUT_ADD_WIDGET, REASON],
                [SEPARATOR_CREATE],
                [SEPARATOR_SET_FRAME_SHAPE, SEPARATOR_FRAME_SHAPE],
                [LAYOUT_ADD_WIDGET, SEPARATOR],
            ]
        )
        self.details = details_text(
            symbol,
            cost_usd,
            price,
            amount_asset,
            holdings_before,
            target_balance,
        )
        self.calls.extend(
            [
                [DETAILS_CREATE, self.details],
                [DETAILS_SET_TEXT_FORMAT, DETAILS_TEXT_FORMAT],
                [DETAILS_SET_STYLE_SHEET, DETAILS_STYLE],
                [LAYOUT_ADD_WIDGET, DETAILS],
                [ROW_CREATE],
                [YES_CREATE, YES_TEXT],
                [NO_CREATE, NO_TEXT],
                [SKIP_CREATE, SKIP_TEXT],
                [YES_SET_STYLE_SHEET, YES_STYLE],
                [NO_SET_STYLE_SHEET, NO_STYLE],
                [SKIP_SET_STYLE_SHEET, SKIP_STYLE],
                [ROW_ADD_WIDGET, YES],
                [ROW_ADD_WIDGET, NO],
                [ROW_ADD_WIDGET, SKIP],
                [LAYOUT_ADD_LAYOUT, BUTTON_ROW],
            ]
        )

    def answer(self, value: str) -> None:
        """Press one button: keep its answer and accept the dialog."""
        self.result_value = value
        self.accepted = True
        self.calls.append([DIALOG_RESULT_VALUE, value])
        self.calls.append([DIALOG_ACCEPT])

    def answer_yes(self) -> None:
        """Press Yes."""
        self.answer(ANSWER_YES)

    def answer_no(self) -> None:
        """Press No."""
        self.answer(ANSWER_NO)

    def answer_skip(self) -> None:
        """Press Skip."""
        self.answer(ANSWER_SKIP)

    def request(
        self,
        bot_id: str,
        symbol: str,
        reason: str,
        cost_usd: float,
        price: float,
        amount_asset: float,
        holdings_before: float,
        target_balance: float,
        loop: Any = None,
        future: Any = None,
        loop_time: float = 0.0,
        timeout_sec: float = TIMEOUT_SEC,
    ) -> dict:
        """File one pending request and hand back the payload it carries."""
        key = request_id(bot_id, millis_of(loop_time))
        payload = {
            "request_id": key,
            "bot_id": bot_id,
            "symbol": symbol,
            "reason": reason,
            "cost_usd": cost_usd,
            "price": price,
            "amount_asset": amount_asset,
            "holdings_before": holdings_before,
            "target_balance": target_balance,
            "loop": loop,
            "future": future,
        }
        self.calls.append([FUTURE_CREATE])
        self.pending[key] = payload
        self.calls.append([PENDING_SET, key])
        self.calls.append([SIGNAL_EMIT, key])
        self.calls.append([WAIT_FOR, timeout_sec])
        return payload

    def timed_out(self, bot_id: str, key: str, timeout_sec: float) -> str:
        """No operator answered inside the wait: drop the request, refuse.

        The request is dropped first, so a late answer cannot resolve a
        buy the bot has already given up on.
        """
        self.pending.pop(key, None)
        self.calls.append([PENDING_POP, key])
        logger.warning(TIMEOUT_LOG, timeout_sec, bot_id)
        return ANSWER_TIMEOUT

    def show_request(
        self,
        payload: dict,
        exec_result: str = ACCEPTED,
        button: Optional[str] = None,
        future_done: bool = False,
    ) -> str:
        """Raise the modal for one request and resolve its answer.

        A dialog closed by its window button counts as ``no``, and a
        future already resolved is left alone rather than raising a
        second time. The pending request is dropped either way.
        """
        self.build(
            payload["symbol"],
            payload["reason"],
            payload["cost_usd"],
            payload["price"],
            payload["amount_asset"],
            payload["holdings_before"],
            payload["target_balance"],
        )
        self.calls.append([DIALOG_SET_WINDOW_FLAG, STAYS_ON_TOP_FLAG, STAYS_ON_TOP])
        self.calls.append([DIALOG_RAISE])
        self.calls.append([DIALOG_ACTIVATE])
        self.calls.append([DIALOG_EXEC])
        if button is not None:
            self.answer(BUTTON_ANSWERS[button])
        self.calls.append([DIALOG_EXEC_RESULT, exec_result])
        if exec_result == ACCEPTED:
            answer = self.result_value
        else:
            answer = CLOSED_ANSWER
        self.calls.append([FUTURE_DONE, future_done])
        if not future_done:
            self.calls.append([FUTURE_SET_RESULT, answer])
        self.pending.pop(payload["request_id"], None)
        self.calls.append([PENDING_POP, payload["request_id"]])
        return answer


PANE_MODEL = BuyConfirmationModel()


def build_view_model(
    model: BuyConfirmationModel,
    symbol: str = "",
    reason: str = "",
    cost_usd: float = 0.0,
    price: float = 0.0,
    amount_asset: float = 0.0,
    holdings_before: float = 0.0,
    target_balance: float = 0.0,
    button: Optional[str] = None,
) -> dict:
    """Return the whole surface state as one serialisable dict."""
    model.build(
        symbol,
        reason,
        cost_usd,
        price,
        amount_asset,
        holdings_before,
        target_balance,
    )
    if button is not None:
        model.answer(BUTTON_ANSWERS[button])
    return {
        "widget": dict(WIDGET),
        "layout": dict(LAYOUT),
        "button_row": dict(BUTTON_ROW_LAYOUT),
        "reason_label": dict(REASON_LABEL),
        "separator": dict(SEPARATOR_FRAME),
        "details_label": dict(DETAILS_LABEL),
        "buttons": {name: dict(spec) for name, spec in BUTTONS.items()},
        "actions": dict(ACTIONS),
        "answers": list(ANSWERS),
        "button_answers": dict(BUTTON_ANSWERS),
        "default_answer": DEFAULT_ANSWER,
        "closed_answer": CLOSED_ANSWER,
        "headless_answer": HEADLESS_ANSWER,
        "timeout_sec": TIMEOUT_SEC,
        "timeout_ms": TIMEOUT_MS,
        "request_fields": list(REQUEST_FIELDS),
        "payload_fields": list(PAYLOAD_FIELDS),
        "dialog_fields": list(DIALOG_FIELDS),
        "reason_text": model.reason_text,
        "details_text": model.details,
        "detail_row_order": list(DETAIL_ROW_ORDER),
        "detail_row_labels": dict(DETAIL_ROW_LABELS),
        "detail_row_values": detail_row_values(
            symbol,
            cost_usd,
            price,
            amount_asset,
            holdings_before,
            target_balance,
        ),
        "result_value": model.result_value,
        "accepted": model.accepted,
        "calls": [list(call) for call in model.calls],
        "reason_color": list(rgb(REASON_COLOR)),
        "yes_surface": list(rgb(YES_SURFACE)),
        "no_surface": list(rgb(NO_SURFACE)),
        "button_text_color": list(rgb(BUTTON_TEXT_COLOR)),
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``buy_confirmation.state``.

    Reads ``reset``, the seven dialog fields and ``button`` from the
    request parameters. The answer persists between calls because the
    dialog's own does; ``reset`` is what a fresh request sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = BuyConfirmationModel()
    return build_view_model(
        PANE_MODEL,
        params.get("symbol", ""),
        params.get("reason", ""),
        params.get("cost_usd", 0.0),
        params.get("price", 0.0),
        params.get("amount_asset", 0.0),
        params.get("holdings_before", 0.0),
        params.get("target_balance", 0.0),
        params.get("button"),
    )

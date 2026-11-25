"""What one decision hands ``BotContainer.order_refusal`` at each of its reads."""

from __future__ import annotations

from dataclasses import dataclass

from ...core.price_age import PriceRead, first_wait
from .config import PRESS_AGAIN

#: What every line and box that refuses a press over the age of a price says last.
PRESS_AGAIN_FRESH = "Nothing is kept, so press it again once a fresh price is in"


@dataclass
class OrderWatch:
    """One decision's reads of ``BotContainer.order_refusal``.

    ``trips`` as it began, ``reads`` the prices it stands on, empty where no price
    decides it, ``press`` true for an operator's press, ``refusal`` why
    ``guarded_place_order`` stopped its newest send, and ``aged`` that text where the
    age of a price stopped it.
    """

    trips: int
    reads: tuple[PriceRead, ...]
    press: bool = False
    refusal: str = ""
    aged: str = ""

    def price_wait(self) -> str:
        """Why no order starts on ``reads`` now, empty while one may."""
        return first_wait(self.reads)

    @property
    def held_by_age(self) -> bool:
        """True where the newest send stopped over the age of a price."""
        return bool(self.aged) and self.aged == self.refusal

    def press_again(self) -> str:
        """What the line that refuses this press says last."""
        return PRESS_AGAIN_FRESH if self.held_by_age else PRESS_AGAIN
